// baryonengine.com: optional. Adds a copy button to each open receipt. No network.
const ru = document.documentElement.lang === "ru";
const W = ru ? { copy: "Скопировать квитанцию", done: "Скопировано", sel: "Выделено: нажмите «Копировать»" }
             : { copy: "Copy receipt", done: "Copied", sel: "Selected: press Copy" };
for (const pre of document.querySelectorAll(".receipt pre")) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "copy";
  button.textContent = W.copy;
  button.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(pre.textContent);
      button.textContent = W.done;
    } catch {
      getSelection().selectAllChildren(pre);
      button.textContent = W.sel;
    }
    setTimeout(() => { button.textContent = W.copy; }, 2000);
  });
  pre.after(button);
}
