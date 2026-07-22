/* 상품 사진 뷰어(라이트박스)
   - 대표 사진이나 썸네일을 클릭하면 큰 화면으로 뜬다.
   - 사진이 여러 장이면 ‹ › 화살표(또는 키보드 방향키)로 넘긴다.
   - 이미지 주소는 서버가 내려준 목록(#gallery-data)만 사용한다. */
(function () {
  var dataEl = document.getElementById("gallery-data");
  if (!dataEl) return;

  // 줄바꿈으로 구분된 이미지 URL 목록
  var urls = dataEl.textContent.split("\n").map(function (s) { return s.trim(); })
                               .filter(function (s) { return s.length > 0; });
  if (urls.length === 0) return;

  var main = document.getElementById("gallery-main");
  var thumbs = document.querySelectorAll(".gallery-thumb");
  var viewer = document.getElementById("viewer");
  var viewerImg = document.getElementById("viewer-img");
  var countEl = document.getElementById("viewer-count");
  var cur = 0;

  function setMain(i) {
    cur = (i + urls.length) % urls.length;
    if (main) main.src = urls[cur];
    thumbs.forEach(function (t, idx) { t.classList.toggle("active", idx === cur); });
  }

  function openViewer(i) {
    cur = (i + urls.length) % urls.length;
    viewerImg.src = urls[cur];
    if (countEl) countEl.textContent = (cur + 1) + " / " + urls.length;
    viewer.hidden = false;
  }
  function closeViewer() { viewer.hidden = true; }
  function show(i) {
    cur = (i + urls.length) % urls.length;
    viewerImg.src = urls[cur];
    if (countEl) countEl.textContent = (cur + 1) + " / " + urls.length;
    setMain(cur);
  }

  // 대표 사진 클릭 → 뷰어 열기
  if (main) main.addEventListener("click", function () { openViewer(cur); });

  // 썸네일: 클릭하면 대표 사진 교체, 한 번 더(또는 바로) 크게 보기
  thumbs.forEach(function (t) {
    t.addEventListener("click", function () {
      var i = parseInt(t.getAttribute("data-index"), 10) || 0;
      setMain(i);
    });
  });

  // 뷰어 컨트롤
  var prev = document.getElementById("viewer-prev");
  var next = document.getElementById("viewer-next");
  var closeBtn = document.getElementById("viewer-close");
  if (prev) prev.addEventListener("click", function (e) { e.stopPropagation(); show(cur - 1); });
  if (next) next.addEventListener("click", function (e) { e.stopPropagation(); show(cur + 1); });
  if (closeBtn) closeBtn.addEventListener("click", closeViewer);
  if (viewer) viewer.addEventListener("click", function (e) {
    if (e.target === viewer) closeViewer();   // 배경 클릭 시 닫기
  });

  // 키보드: ← → 넘기기, Esc 닫기
  document.addEventListener("keydown", function (e) {
    if (viewer.hidden) return;
    if (e.key === "ArrowLeft") show(cur - 1);
    else if (e.key === "ArrowRight") show(cur + 1);
    else if (e.key === "Escape") closeViewer();
  });
})();
