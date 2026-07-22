/* 실시간 채팅 클라이언트
   - 받은 메시지는 항상 textContent 로만 넣는다(innerHTML 금지) → XSS 방지.
   - 날짜가 바뀌면 구분선을 넣고, 메시지마다 시간과 보낸이 프로필 링크를 표시한다.
   - 사진은 먼저 서버(/chat/upload)에 올려 검증받은 뒤, 그 파일명만 소켓으로 전송한다. */
(function () {
  var chatEl = document.getElementById("chat");
  if (!chatEl) return;

  var room = chatEl.getAttribute("data-room");
  var csrf = chatEl.getAttribute("data-csrf");
  var box = document.getElementById("chat-box");
  var form = document.getElementById("chat-form");
  var input = document.getElementById("chat-input");
  var photoInput = document.getElementById("chat-photo");

  // 서버가 이미 그려준 마지막 날짜 구분선을 읽어 초기값으로 둔다.
  var dateEls = box.querySelectorAll(".chat-date span");
  var lastDate = dateEls.length ? dateEls[dateEls.length - 1].textContent : "";

  var socket = io();
  socket.on("connect", function () { socket.emit("join", { room: room }); });
  socket.on("new_message", function (data) { appendMessage(data); });

  // 글 전송
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var content = input.value.trim();
    if (!content) return;
    socket.emit("send_message", { room: room, content: content });
    input.value = "";
  });

  // 사진 전송: 업로드 → 검증된 파일명 받기 → 소켓으로 그 파일명만 전송
  if (photoInput) {
    photoInput.addEventListener("change", function () {
      var file = photoInput.files[0];
      if (!file) return;
      var fd = new FormData();
      fd.append("image", file);
      fetch("/chat/upload", {
        method: "POST",
        headers: { "X-CSRFToken": csrf },   // CSRF 토큰(헤더) 검증
        body: fd,
      }).then(function (r) { return r.json(); })
        .then(function (res) {
          if (res.ok) socket.emit("send_message", { room: room, image: res.path });
          else alert(res.error || "사진을 보낼 수 없어요.");
        })
        .catch(function () { alert("사진 업로드 중 문제가 생겼어요."); })
        .finally(function () { photoInput.value = ""; });
    });
  }

  function insertDate(d) {
    var wrap = document.createElement("div");
    wrap.className = "chat-date";
    var span = document.createElement("span");
    span.textContent = d;
    wrap.appendChild(span);
    box.appendChild(wrap);
  }

  function appendMessage(data) {
    if (data.date && data.date !== lastDate) {
      insertDate(data.date);
      lastDate = data.date;
    }

    var wrap = document.createElement("div");
    wrap.className = "chat-msg";

    // 보낸이 이름 → 프로필로 가는 링크
    var who = document.createElement("span");
    who.className = "who";
    var a = document.createElement("a");
    a.href = "/user/" + data.sender_id;
    a.textContent = data.username;    // textContent → 태그가 문자로만 표시됨
    who.appendChild(a);
    wrap.appendChild(who);

    if (data.image) {
      var img = document.createElement("img");
      img.className = "chat-img";
      img.alt = "사진";
      img.src = "/static/uploads/" + data.image;
      wrap.appendChild(img);
    } else {
      wrap.appendChild(document.createTextNode(data.content));
    }

    if (data.time) {
      var t = document.createElement("span");
      t.className = "time";
      t.textContent = data.time;
      wrap.appendChild(t);
    }

    box.appendChild(wrap);
    box.scrollTop = box.scrollHeight;
  }

  // 채팅 사진을 클릭하면 큰 화면으로 보기(간단한 오버레이)
  box.addEventListener("click", function (e) {
    if (e.target && e.target.classList.contains("chat-img")) {
      openImage(e.target.src);
    }
  });
  function openImage(src) {
    var ov = document.createElement("div");
    ov.className = "viewer";
    var img = document.createElement("img");
    img.className = "viewer-img";
    img.src = src;
    ov.appendChild(img);
    ov.addEventListener("click", function () { document.body.removeChild(ov); });
    document.body.appendChild(ov);
  }

  box.scrollTop = box.scrollHeight;
})();
