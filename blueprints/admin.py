"""
관리자 기능: 대시보드에서 신고 내역을 확인하고 상품/사용자를 관리한다.

모든 라우트에 @admin_required 를 걸어, 관리자가 아닌 사용자가 URL 을 직접
입력해도 접근하지 못하도록(수평/수직 권한 상승 차단) 했다.
상태를 바꾸는 동작은 전부 POST + CSRF 토큰으로만 수행한다.
"""
from flask import Blueprint, render_template, redirect, url_for, flash, abort

from db import query, execute
from security import admin_required

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/")
@admin_required
def dashboard():
    users = query("SELECT * FROM users ORDER BY report_count DESC, created_at DESC")
    products = query(
        """SELECT p.*, u.username AS seller_name
             FROM products p JOIN users u ON u.id = p.seller_id
            ORDER BY p.report_count DESC, p.created_at DESC""",
    )
    reports = query(
        """SELECT r.*, u.username AS reporter_name
             FROM reports r JOIN users u ON u.id = r.reporter_id
            ORDER BY r.created_at DESC LIMIT 100""",
    )
    return render_template("admin.html", users=users, products=products, reports=reports)


@bp.route("/product/<product_id>/toggle", methods=["POST"])
@admin_required
def toggle_product(product_id):
    """상품 숨김/해제 토글."""
    product = query("SELECT is_blocked FROM products WHERE id = ?", (product_id,), one=True)
    if product is None:
        abort(404)
    new_state = 0 if product["is_blocked"] else 1
    execute("UPDATE products SET is_blocked = ? WHERE id = ?", (new_state, product_id))
    flash("상품 상태를 변경했습니다.")
    return redirect(url_for("admin.dashboard"))


@bp.route("/product/<product_id>/delete", methods=["POST"])
@admin_required
def delete_product(product_id):
    execute("DELETE FROM products WHERE id = ?", (product_id,))
    flash("상품을 삭제했습니다.")
    return redirect(url_for("admin.dashboard"))


@bp.route("/user/<user_id>/toggle", methods=["POST"])
@admin_required
def toggle_user(user_id):
    """사용자 휴면/복구 토글. 관리자 계정은 휴면 처리하지 못하게 막는다."""
    user = query("SELECT is_dormant, is_admin FROM users WHERE id = ?", (user_id,), one=True)
    if user is None:
        abort(404)
    if user["is_admin"]:
        flash("관리자 계정은 휴면 처리할 수 없습니다.")
        return redirect(url_for("admin.dashboard"))
    new_state = 0 if user["is_dormant"] else 1
    # 복구 시 누적 신고 수도 초기화해준다.
    if new_state == 0:
        execute("UPDATE users SET is_dormant = 0, report_count = 0 WHERE id = ?", (user_id,))
    else:
        execute("UPDATE users SET is_dormant = 1 WHERE id = ?", (user_id,))
    flash("사용자 상태를 변경했습니다.")
    return redirect(url_for("admin.dashboard"))
