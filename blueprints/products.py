"""
상품 관리: 목록/검색 / 등록 / 상세 / 수정 / 삭제 / 내 상품.
상품 사진은 여러 장 등록할 수 있고, product_images 테이블에 순서대로 저장한다.
"""
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, abort, current_app
)

from db import query, execute
from security import (
    clean_text, current_user, login_required, safe_image_save, new_id
)

bp = Blueprint("products", __name__)


def _save_images(product_id, files, start_order=0):
    """
    업로드된 파일 여러 개를 검증 후 product_images 에 저장한다.
    - 최대 장수(MAX_PRODUCT_IMAGES)를 넘으면 앞에서부터만 저장
    - 각 파일은 safe_image_save 로 '실제 이미지인지'까지 검증
    반환: 저장된 파일명 리스트(첫 장이 대표 이미지)
    """
    saved = []
    limit = current_app.config["MAX_PRODUCT_IMAGES"]
    order = start_order
    for f in files:
        if len(saved) + start_order >= limit:
            break
        if not f or not f.filename:
            continue
        name = safe_image_save(f)
        if name is None:
            # 이미지가 아닌 파일이 섞이면 건너뛴다(전체 실패시키지 않음)
            continue
        execute(
            "INSERT INTO product_images (id, product_id, image_path, sort_order) VALUES (?, ?, ?, ?)",
            (new_id(), product_id, name, order),
        )
        saved.append(name)
        order += 1
    return saved


@bp.route("/")
def index():
    """
    전체 상품 조회 + 검색.
    검색어는 LIKE 파라미터 바인딩으로 넘겨 SQL Injection 을 막고,
    와일드카드 문자(%, _)는 이스케이프 처리한다.
    """
    keyword = clean_text(request.args.get("q", ""), 50)

    if keyword:
        # LIKE 특수문자 이스케이프 후 바인딩
        escaped = keyword.replace("!", "!!").replace("%", "!%").replace("_", "!_")
        like = f"%{escaped}%"
        products = query(
            """SELECT p.*, u.username AS seller_name
                 FROM products p JOIN users u ON u.id = p.seller_id
                WHERE p.is_blocked = 0
                  AND (p.title LIKE ? ESCAPE '!' OR p.description LIKE ? ESCAPE '!')
                ORDER BY p.created_at DESC""",
            (like, like),
        )
    else:
        products = query(
            """SELECT p.*, u.username AS seller_name
                 FROM products p JOIN users u ON u.id = p.seller_id
                WHERE p.is_blocked = 0
                ORDER BY p.created_at DESC""",
        )

    return render_template("index.html", products=products,
                           keyword=keyword, me=current_user())


@bp.route("/product/new", methods=["GET", "POST"])
@login_required
def create():
    user = current_user()
    if request.method == "POST":
        title = clean_text(request.form.get("title", ""), 100)
        description = clean_text(request.form.get("description", ""), 2000)
        price_raw = request.form.get("price", "").strip()

        # 필수값/형식 검증
        if not title or not description:
            flash("상품명과 설명을 입력해 주세요.")
            return render_template("product_form.html", mode="new", form=request.form)

        # 가격은 반드시 정수 + 허용 범위 안(음수/천문학적 값 차단)
        try:
            price = int(price_raw)
        except ValueError:
            flash("가격은 숫자로 입력해 주세요.")
            return render_template("product_form.html", mode="new", form=request.form)
        if not (current_app.config["MIN_PRICE"] <= price <= current_app.config["MAX_PRICE"]):
            flash("가격이 허용 범위를 벗어났습니다.")
            return render_template("product_form.html", mode="new", form=request.form)

        pid = new_id()
        # 상품을 먼저 만들고(외래키 때문에), 사진 여러 장을 저장한다.
        execute(
            """INSERT INTO products (id, title, description, price, seller_id, image_path)
               VALUES (?, ?, ?, ?, ?, NULL)""",
            (pid, title, description, price, user["id"]),
        )
        images = _save_images(pid, request.files.getlist("images"))
        if images:
            # 첫 장을 대표 이미지로 지정(목록 썸네일용)
            execute("UPDATE products SET image_path = ? WHERE id = ?", (images[0], pid))
        flash("상품이 등록되었습니다.")
        return redirect(url_for("products.detail", product_id=pid))

    return render_template("product_form.html", mode="new", form={})


@bp.route("/product/<product_id>")
def detail(product_id):
    product = query(
        """SELECT p.*, u.username AS seller_name
             FROM products p JOIN users u ON u.id = p.seller_id
            WHERE p.id = ?""",
        (product_id,), one=True,
    )
    if product is None:
        abort(404)

    me = current_user()
    # 차단된 상품은 판매자 본인/관리자만 볼 수 있다.
    if product["is_blocked"]:
        if me is None or (me["id"] != product["seller_id"] and not me["is_admin"]):
            abort(404)

    # 갤러리용 이미지 목록(순서대로). 없으면 대표 이미지라도 사용.
    images = query(
        "SELECT image_path FROM product_images WHERE product_id = ? ORDER BY sort_order",
        (product_id,),
    )
    image_list = [row["image_path"] for row in images]
    if not image_list and product["image_path"]:
        image_list = [product["image_path"]]

    is_owner = bool(me and me["id"] == product["seller_id"])
    return render_template("product_detail.html", product=product,
                           images=image_list, me=me, is_owner=is_owner)


@bp.route("/product/<product_id>/edit", methods=["GET", "POST"])
@login_required
def edit(product_id):
    user = current_user()
    product = query("SELECT * FROM products WHERE id = ?", (product_id,), one=True)
    if product is None:
        abort(404)
    # 소유자 확인: 남의 상품을 수정하지 못하게 막는다(접근 통제).
    if product["seller_id"] != user["id"] and not user["is_admin"]:
        abort(403)

    if request.method == "POST":
        title = clean_text(request.form.get("title", ""), 100)
        description = clean_text(request.form.get("description", ""), 2000)
        try:
            price = int(request.form.get("price", "").strip())
        except ValueError:
            flash("가격은 숫자로 입력해 주세요.")
            return render_template("product_form.html", mode="edit", form=request.form, product=product)
        if not title or not description:
            flash("상품명과 설명을 입력해 주세요.")
            return render_template("product_form.html", mode="edit", form=request.form, product=product)
        if not (current_app.config["MIN_PRICE"] <= price <= current_app.config["MAX_PRICE"]):
            flash("가격이 허용 범위를 벗어났습니다.")
            return render_template("product_form.html", mode="edit", form=request.form, product=product)

        execute(
            "UPDATE products SET title = ?, description = ?, price = ? WHERE id = ?",
            (title, description, price, product_id),
        )
        # 새로 올린 사진이 있으면 기존 사진 뒤에 추가한다.
        existing = query(
            "SELECT COUNT(*) AS c FROM product_images WHERE product_id = ?",
            (product_id,), one=True,
        )["c"]
        _save_images(product_id, request.files.getlist("images"), start_order=existing)
        # 대표 이미지가 비어 있으면 첫 사진으로 채운다.
        first = query(
            "SELECT image_path FROM product_images WHERE product_id = ? ORDER BY sort_order LIMIT 1",
            (product_id,), one=True,
        )
        execute("UPDATE products SET image_path = ? WHERE id = ?",
                (first["image_path"] if first else None, product_id))
        flash("상품 정보가 수정되었습니다.")
        return redirect(url_for("products.detail", product_id=product_id))

    return render_template("product_form.html", mode="edit", form=product, product=product)


@bp.route("/product/<product_id>/delete", methods=["POST"])
@login_required
def delete(product_id):
    user = current_user()
    product = query("SELECT * FROM products WHERE id = ?", (product_id,), one=True)
    if product is None:
        abort(404)
    if product["seller_id"] != user["id"] and not user["is_admin"]:
        abort(403)
    execute("DELETE FROM products WHERE id = ?", (product_id,))
    flash("상품이 삭제되었습니다.")
    return redirect(url_for("products.mine"))


@bp.route("/my/products")
@login_required
def mine():
    user = current_user()
    products = query(
        "SELECT * FROM products WHERE seller_id = ? ORDER BY created_at DESC",
        (user["id"],),
    )
    return render_template("my_products.html", products=products)
