(function () {
  const STYLE_ID = "criclytics-toast-styles";
  const ROOT_ID = "criclytics-toast-root";
  const TOAST_TYPES = {
    success: { label: "Success", accent: "94 234 212", duration: 4200, role: "status" },
    error: { label: "Error", accent: "248 113 113", duration: 7600, role: "alert" },
    warning: { label: "Warning", accent: "251 191 36", duration: 6200, role: "alert" },
    info: { label: "Info", accent: "96 165 250", duration: 4800, role: "status" },
  };

  const activeToasts = new Map();

  function ensureStyles() {
    if (document.getElementById(STYLE_ID)) {
      return;
    }

    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
      #${ROOT_ID} {
        position: fixed;
        top: 1rem;
        right: 1rem;
        z-index: 70;
        display: flex;
        width: min(26rem, calc(100vw - 2rem));
        flex-direction: column;
        gap: 0.75rem;
        pointer-events: none;
      }

      .criclytics-toast {
        pointer-events: auto;
        position: relative;
        overflow: hidden;
        border-radius: 1rem;
        border: 1px solid rgb(var(--color-line) / 0.52);
        background: rgb(var(--color-panel) / 0.97);
        box-shadow: var(--panel-shadow);
        color: rgb(var(--color-copy));
        transform: translateY(-8px);
        opacity: 0;
        transition: opacity 160ms ease, transform 160ms ease;
      }

      .criclytics-toast.is-visible {
        transform: translateY(0);
        opacity: 1;
      }

      .criclytics-toast::before {
        content: "";
        position: absolute;
        top: 0;
        left: 0;
        bottom: 0;
        width: 3px;
        background: rgb(var(--toast-accent));
      }

      .criclytics-toast__body {
        padding: 0.95rem 1rem 0.95rem 1rem;
      }

      .criclytics-toast__header {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 0.75rem;
      }

      .criclytics-toast__eyebrow {
        margin: 0 0 0.25rem;
        font-size: 0.68rem;
        font-weight: 800;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: rgb(var(--toast-accent));
      }

      .criclytics-toast__title {
        margin: 0;
        font-size: 0.95rem;
        font-weight: 700;
        line-height: 1.35;
      }

      .criclytics-toast__message {
        margin: 0.35rem 0 0;
        font-size: 0.84rem;
        line-height: 1.55;
        color: rgb(var(--color-muted));
      }

      .criclytics-toast__details {
        margin: 0.6rem 0 0;
        padding-left: 1rem;
        font-size: 0.78rem;
        line-height: 1.5;
        color: rgb(var(--color-soft));
      }

      .criclytics-toast__details li + li {
        margin-top: 0.18rem;
      }

      .criclytics-toast__close {
        display: inline-flex;
        height: 1.9rem;
        width: 1.9rem;
        align-items: center;
        justify-content: center;
        border: 0;
        border-radius: 9999px;
        background: transparent;
        color: rgb(var(--color-soft));
        cursor: pointer;
        transition: background-color 120ms ease, color 120ms ease;
      }

      .criclytics-toast__close:hover {
        background: rgb(var(--color-line) / 0.2);
        color: rgb(var(--color-copy));
      }

      .criclytics-toast__close:focus-visible {
        outline: 2px solid rgb(var(--toast-accent) / 0.42);
        outline-offset: 2px;
      }

      .criclytics-toast__progress {
        position: absolute;
        right: 0;
        bottom: 0;
        height: 2px;
        width: 100%;
        background: rgb(var(--toast-accent) / 0.18);
        transform-origin: left center;
      }

      .criclytics-toast__progress.is-animating {
        animation: criclytics-toast-progress linear forwards;
        animation-duration: var(--toast-duration, 4000ms);
      }

      @keyframes criclytics-toast-progress {
        from {
          transform: scaleX(1);
        }
        to {
          transform: scaleX(0);
        }
      }

      @media (max-width: 640px) {
        #${ROOT_ID} {
          left: 0.75rem;
          right: 0.75rem;
          width: auto;
        }
      }
    `;
    document.head.appendChild(style);
  }

  function ensureRoot() {
    let root = document.getElementById(ROOT_ID);
    if (!root) {
      root = document.createElement("div");
      root.id = ROOT_ID;
      root.setAttribute("aria-live", "polite");
      root.setAttribute("aria-relevant", "additions");
      document.body.appendChild(root);
    }
    return root;
  }

  function signatureFor(options) {
    if (options.id) {
      return options.id;
    }
    return [
      options.type,
      options.title,
      options.message,
      ...(options.details || []),
    ].join("|");
  }

  function dismiss(signature) {
    const entry = activeToasts.get(signature);
    if (!entry) {
      return;
    }

    window.clearTimeout(entry.timeoutId);
    entry.element.classList.remove("is-visible");
    window.setTimeout(() => {
      entry.element.remove();
      activeToasts.delete(signature);
    }, 180);
  }

  function createDetailList(details) {
    if (!details || details.length === 0) {
      return null;
    }

    const list = document.createElement("ul");
    list.className = "criclytics-toast__details";
    details.forEach((detail) => {
      const item = document.createElement("li");
      item.textContent = detail;
      list.appendChild(item);
    });
    return list;
  }

  function show(input) {
    const options = {
      type: input.type || "info",
      title: input.title || TOAST_TYPES[input.type || "info"].label,
      message: input.message || "",
      details: Array.isArray(input.details) ? input.details.filter(Boolean) : [],
      sticky: Boolean(input.sticky),
    };
    const config = TOAST_TYPES[options.type] || TOAST_TYPES.info;
    const signature = signatureFor(options);

    if (activeToasts.has(signature)) {
      dismiss(signature);
    }

    ensureStyles();
    const root = ensureRoot();

    const toast = document.createElement("section");
    toast.className = "criclytics-toast";
    toast.dataset.type = options.type;
    toast.style.setProperty("--toast-accent", config.accent);
    toast.style.setProperty("--toast-duration", `${input.duration || config.duration}ms`);
    toast.setAttribute("role", config.role);

    const body = document.createElement("div");
    body.className = "criclytics-toast__body";

    const header = document.createElement("div");
    header.className = "criclytics-toast__header";

    const copy = document.createElement("div");

    const eyebrow = document.createElement("p");
    eyebrow.className = "criclytics-toast__eyebrow";
    eyebrow.textContent = config.label;

    const title = document.createElement("p");
    title.className = "criclytics-toast__title";
    title.textContent = options.title;

    copy.appendChild(eyebrow);
    copy.appendChild(title);

    if (options.message) {
      const message = document.createElement("p");
      message.className = "criclytics-toast__message";
      message.textContent = options.message;
      copy.appendChild(message);
    }

    const detailList = createDetailList(options.details);
    if (detailList) {
      copy.appendChild(detailList);
    }

    const closeButton = document.createElement("button");
    closeButton.type = "button";
    closeButton.className = "criclytics-toast__close";
    closeButton.setAttribute("aria-label", "Dismiss notification");
    closeButton.textContent = "x";
    closeButton.addEventListener("click", () => dismiss(signature));

    header.appendChild(copy);
    header.appendChild(closeButton);
    body.appendChild(header);
    toast.appendChild(body);

    if (!options.sticky) {
      const progress = document.createElement("div");
      progress.className = "criclytics-toast__progress is-animating";
      toast.appendChild(progress);
    }

    root.prepend(toast);
    requestAnimationFrame(() => {
      toast.classList.add("is-visible");
    });

    const timeoutId = options.sticky
      ? null
      : window.setTimeout(() => dismiss(signature), input.duration || config.duration);

    activeToasts.set(signature, { element: toast, timeoutId });
    return signature;
  }

  window.CriclyticsToast = {
    show,
    dismiss,
    clear() {
      Array.from(activeToasts.keys()).forEach((signature) => dismiss(signature));
    },
    success(options) {
      return show({ ...options, type: "success" });
    },
    error(options) {
      return show({ ...options, type: "error" });
    },
    warning(options) {
      return show({ ...options, type: "warning" });
    },
    info(options) {
      return show({ ...options, type: "info" });
    },
  };
})();
