(function () {
  const popup = document.getElementById("popup");
  function sessionId() {
    return (window.ERA && window.ERA.sessionId) || 0;
  }

  function place(el, html) {
    popup.innerHTML = html;
    popup.hidden = false;
    const r = el.getBoundingClientRect();
    popup.style.left = Math.min(window.scrollX + r.left, window.scrollX + window.innerWidth - 320) + "px";
    popup.style.top = window.scrollY + r.bottom + 8 + "px";
  }

  document.addEventListener("click", async (ev) => {
    const unk = ev.target.closest(".unknown");
    if (unk) {
      const params = new URLSearchParams({
        session_id: sessionId(),
        sentence_id: unk.dataset.sentenceId,
        lemma: unk.dataset.lemma,
        surface: unk.dataset.surface,
      });
      const res = await fetch("/api/lookup?" + params.toString());
      place(unk, await res.text());
      return;
    }
    const hint = ev.target.closest(".hint-btn");
    if (hint) {
      const sentence = hint.closest(".sentence");
      const params = new URLSearchParams({
        session_id: sessionId(),
        sentence_id: sentence.dataset.sentenceId,
        level: hint.dataset.level,
      });
      const res = await fetch("/api/hint?" + params.toString());
      const slot = sentence.querySelector(".hint-slot");
      slot.innerHTML = await res.text();
      return;
    }
    if (!popup.contains(ev.target)) popup.hidden = true;
  });
})();
