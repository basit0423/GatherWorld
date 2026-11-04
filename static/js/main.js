// Gather World Phase 1 interactions.
// Password confirmation is checked in the browser and again on the server.
document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("form[data-password-match]").forEach((form) => {
        const password = form.querySelector('input[name="password"]');
        const confirm = form.querySelector('input[name="confirm_password"]');
        const message = form.querySelector("[data-password-message]");
        if (!password || !confirm || !message) return;

        const validate = () => {
            if (!confirm.value) {
                message.textContent = "Use at least 10 characters and make both passwords match.";
                message.classList.remove("is-invalid");
                confirm.setCustomValidity("");
                return true;
            }
            const matches = password.value === confirm.value;
            message.textContent = matches ? "Passwords match." : "The passwords do not match yet.";
            message.classList.toggle("is-invalid", !matches);
            confirm.setCustomValidity(matches ? "" : "The passwords do not match.");
            return matches;
        };
        password.addEventListener("input", validate);
        confirm.addEventListener("input", validate);
        form.addEventListener("submit", (event) => {
            if (!validate()) {
                event.preventDefault();
                confirm.reportValidity();
            }
        });
    });
});


// Local preview for a profile photo before it is sent to Cloudinary.
(() => {
  const input = document.getElementById("avatar-file");
  const preview = document.getElementById("avatar-upload-preview");
  const image = document.getElementById("avatar-preview-image");
  if (!input || !preview || !image) return;
  let previewUrl = null;
  input.addEventListener("change", () => {
    const file = input.files && input.files[0];
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = null;
    if (!file) { preview.hidden = true; return; }
    if (!file.type.startsWith("image/")) { input.value = ""; preview.hidden = true; return; }
    previewUrl = URL.createObjectURL(file);
    image.src = previewUrl;
    preview.hidden = false;
  });
})();


// Gather World share links: copy canonical post URL without requiring an account.
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-copy-url]");
  if (!button) return;
  const value = button.getAttribute("data-copy-url");
  if (!value) return;
  const original = button.textContent;
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(value);
    } else {
      const helper = document.createElement("textarea");
      helper.value = value;
      helper.style.position = "fixed";
      helper.style.opacity = "0";
      document.body.appendChild(helper);
      helper.select();
      const copied = document.execCommand("copy");
      helper.remove();
      if (!copied) throw new Error("Clipboard unavailable");
    }
    button.textContent = "✓ Copied";
    window.setTimeout(() => { button.textContent = original; }, 1800);
  } catch (_) {
    button.textContent = "Copy unavailable";
  }
});

// Keep the Moments page lightweight: pause other videos after one starts.
document.addEventListener("play", (event) => {
  if (event.target && event.target.tagName === "VIDEO") {
    document.querySelectorAll("video").forEach((video) => {
      if (video !== event.target) video.pause();
    });
  }
}, true);


// Gather Moments: filter image/video posts, autoplay only the visible video,
// pause off-screen videos, and provide lightweight play/audio controls.
(() => {
  const feed = document.getElementById("moments-feed");
  if (!feed) return;
  const cards = Array.from(feed.querySelectorAll(".moment-card"));
  const filters = document.querySelectorAll("[data-media-filter]");

  filters.forEach((button) => {
    button.addEventListener("click", () => {
      const filter = button.getAttribute("data-media-filter") || "all";
      filters.forEach((item) => item.classList.toggle("is-active", item === button));
      cards.forEach((card) => {
        card.hidden = filter !== "all" && card.getAttribute("data-media-kind") !== filter;
        const video = card.querySelector("[data-moment-video]");
        if (card.hidden && video) video.pause();
      });
      feed.scrollTo({ top: 0, behavior: "smooth" });
    });
  });

  const videos = cards.map((card) => ({ card, video: card.querySelector("[data-moment-video]") })).filter((x) => x.video);
  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        const video = entry.target;
        const card = video.closest(".moment-card");
        if (!card) return;
        if (entry.isIntersecting && entry.intersectionRatio >= 0.68 && !card.hidden) {
          videos.forEach((item) => {
            if (item.video !== video) { item.video.pause(); item.card.classList.remove("is-paused"); }
          });
          video.play().then(() => card.classList.remove("is-paused")).catch(() => card.classList.add("is-paused"));
        } else {
          video.pause();
        }
      });
    }, { root: feed, threshold: [0, 0.35, 0.68, 0.9] });
    videos.forEach(({ video }) => observer.observe(video));
  }

  feed.addEventListener("click", (event) => {
    const playButton = event.target.closest("[data-toggle-play]");
    if (playButton) {
      const card = playButton.closest(".moment-card");
      const video = card && card.querySelector("[data-moment-video]");
      if (!video) return;
      if (video.paused) video.play().then(() => card.classList.remove("is-paused")).catch(() => card.classList.add("is-paused"));
      else { video.pause(); card.classList.add("is-paused"); }
      return;
    }
    const audioButton = event.target.closest("[data-audio-toggle]");
    if (audioButton) {
      const card = audioButton.closest(".moment-card");
      const video = card && card.querySelector("[data-moment-video]");
      if (!video) return;
      video.muted = !video.muted;
      audioButton.textContent = video.muted ? "♫" : "♪";
      audioButton.setAttribute("aria-label", video.muted ? "Turn sound on" : "Mute video");
      return;
    }
    const stage = event.target.closest("[data-moment-stage]");
    if (stage && !event.target.closest("button,a,form")) {
      const card = stage.closest(".moment-card");
      const video = card && card.querySelector("[data-moment-video]");
      if (video) {
        if (video.paused) video.play().then(() => card.classList.remove("is-paused")).catch(() => card.classList.add("is-paused"));
        else { video.pause(); card.classList.add("is-paused"); }
      }
    }
  });

  videos.forEach(({ card, video }) => {
    video.addEventListener("pause", () => card.classList.add("is-paused"));
    video.addEventListener("playing", () => card.classList.remove("is-paused"));
  });
})();


// Gather World post composer: local image/video preview before secure Cloudinary upload.
(() => {
  const inputs = Array.from(document.querySelectorAll("input[data-post-media]"));
  const preview = document.getElementById("post-media-preview");
  const image = document.getElementById("post-photo-preview");
  const video = document.getElementById("post-video-preview");
  const fileName = document.getElementById("post-file-name");
  const clearButton = document.getElementById("clear-post-media");
  if (!inputs.length || !preview || !image || !video) return;

  let previewUrl = null;
  const clearPreview = () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = null;
    inputs.forEach((input) => { input.value = ""; });
    image.removeAttribute("src");
    video.pause();
    video.removeAttribute("src");
    video.load();
    image.hidden = true;
    video.hidden = true;
    preview.hidden = true;
    if (fileName) fileName.textContent = "";
  };

  inputs.forEach((input) => {
    input.addEventListener("change", () => {
      const file = input.files && input.files[0];
      if (!file) return;
      inputs.forEach((other) => { if (other !== input) other.value = ""; });
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      previewUrl = URL.createObjectURL(file);
      image.hidden = true;
      video.hidden = true;
      if (input.dataset.postMedia === "image") {
        image.src = previewUrl;
        image.hidden = false;
      } else {
        video.src = previewUrl;
        video.hidden = false;
      }
      if (fileName) fileName.textContent = `${file.name} · ${(file.size / (1024 * 1024)).toFixed(1)} MB`;
      preview.hidden = false;
    });
  });
  if (clearButton) clearButton.addEventListener("click", clearPreview);
})();


// Compact navigation shared by standard pages, Home and Moments.
(() => {
  document.querySelectorAll("[data-menu-toggle]").forEach((toggle) => {
    const menuId = toggle.getAttribute("aria-controls");
    const menu = menuId ? document.getElementById(menuId) : null;
    if (!menu) return;
    const closeMenu = (restoreFocus = false) => {
      menu.hidden = true;
      menu.querySelectorAll("details[open]").forEach((item) => { item.open = false; });
      toggle.setAttribute("aria-expanded", "false");
      toggle.setAttribute("aria-label", "Open navigation menu");
      if (restoreFocus) toggle.focus();
    };
    toggle.addEventListener("click", () => {
      const willOpen = menu.hidden;
      menu.hidden = !willOpen;
      toggle.setAttribute("aria-expanded", String(willOpen));
      toggle.setAttribute("aria-label", willOpen ? "Close navigation menu" : "Open navigation menu");
      if (willOpen) {
        const search = menu.querySelector('input[type="search"]');
        if (search && window.matchMedia("(min-width: 720px)").matches) search.focus({preventScroll:true});
      }
    });
    menu.addEventListener("click", (event) => {
      if (event.target.closest("a")) closeMenu(false);
    });
    document.addEventListener("click", (event) => {
      if (!menu.hidden && !menu.contains(event.target) && !toggle.contains(event.target)) closeMenu(false);
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !menu.hidden) closeMenu(true);
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        if (menu.hidden) toggle.click();
        const search = menu.querySelector('input[type="search"]');
        if (search) search.focus();
      }
      if (event.key === "/" && !event.ctrlKey && !event.metaKey && !["INPUT","TEXTAREA","SELECT"].includes(document.activeElement.tagName)) {
        const search = menu.querySelector('input[type="search"]');
        if (search) { event.preventDefault(); if (menu.hidden) toggle.click(); search.focus(); }
      }
    });
  });
})();


// Gather World appearance: System / Light / Dark. User choice persists locally.
(() => {
  const root = document.documentElement;
  const key = "gather-theme-mode";
  const legacyKey = "gather-theme";
  const modes = ["system", "light", "dark"];
  const systemTheme = () => window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  const getMode = () => {
    try {
      const saved = localStorage.getItem(key);
      if (modes.includes(saved)) return saved;
      const legacy = localStorage.getItem(legacyKey);
      if (legacy === "light" || legacy === "dark") return legacy;
    } catch (_) {}
    return "system";
  };
  const apply = (mode, persist = false) => {
    const effective = mode === "system" ? systemTheme() : mode;
    root.dataset.themeMode = mode;
    root.dataset.theme = effective;
    document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
      const label = mode === "system" ? "System" : mode === "light" ? "Light" : "Dark";
      button.textContent = `◐ Theme: ${label}`;
      button.setAttribute("aria-label", `Appearance theme: ${label}. Activate to change theme.`);
      button.setAttribute("aria-pressed", String(mode !== "system"));
      button.title = "Cycle System, Light and Dark appearance";
    });
    const meta = document.getElementById("gather-theme-color");
    if (meta) meta.setAttribute("content", effective === "light" ? "#f5f7fb" : "#101827");
    if (persist) {
      try { localStorage.setItem(key, mode); localStorage.removeItem(legacyKey); } catch (_) {}
    }
  };
  apply(getMode(), false);
  document.addEventListener("click", (event) => {
    if (!event.target.closest("[data-theme-toggle]")) return;
    const current = getMode();
    const next = modes[(modes.indexOf(current) + 1) % modes.length];
    apply(next, true);
  });
  if (window.matchMedia) {
    const media = window.matchMedia("(prefers-color-scheme: light)");
    const updateSystem = () => { if (getMode() === "system") apply("system", false); };
    if (media.addEventListener) media.addEventListener("change", updateSystem);
    else if (media.addListener) media.addListener(updateSystem);
  }
})();
