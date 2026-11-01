// @ts-check

/** Connect category chart buttons to the shared native modal dialog. */
function initializeDetailsDialog() {
  const dialog = document.getElementById("category-details-dialog");
  const body = document.getElementById("details-body");
  const title = document.getElementById("details-title");
  if (!(dialog instanceof HTMLDialogElement) || !body || !title) return;

  document.querySelectorAll("button[data-details-template]").forEach((trigger) => {
    if (!(trigger instanceof HTMLButtonElement)) return;
    trigger.addEventListener("click", () => {
      const template = document.getElementById(trigger.dataset.detailsTemplate ?? "");
      if (!(template instanceof HTMLTemplateElement) || dialog.open) return;
      title.textContent = `${trigger.dataset.category ?? "カテゴリ"}の明細`;
      body.replaceChildren(template.content.cloneNode(true));
      body.scrollTop = 0;
      trigger.focus({ preventScroll: true });
      dialog.showModal();
      document.body.classList.add("modal-open");
    });
  });

  dialog.querySelector("[data-close-details]")?.addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => {
    const bounds = dialog.getBoundingClientRect();
    const outside = event.clientX < bounds.left || event.clientX > bounds.right
      || event.clientY < bounds.top || event.clientY > bounds.bottom;
    if (event.target === dialog && outside) dialog.close();
  });
  dialog.addEventListener("close", () => {
    document.body.classList.remove("modal-open");
    body.replaceChildren();
  });
}

initializeDetailsDialog();
