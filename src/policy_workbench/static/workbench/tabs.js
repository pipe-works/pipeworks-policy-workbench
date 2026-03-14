import { dom } from "./dom.js";

const MAIN_TAB_EDITOR = "editor";
const MAIN_TAB_ACTIVATION = "activation";

function setTabUi({ button, panel, isActive }) {
  if (button) {
    button.classList.toggle("is-active", isActive);
    button.setAttribute("aria-selected", isActive ? "true" : "false");
    button.tabIndex = isActive ? 0 : -1;
  }
  if (panel) {
    panel.hidden = !isActive;
  }
}

export function setActiveMainTab(tabName) {
  const useActivation = tabName === MAIN_TAB_ACTIVATION;
  setTabUi({
    button: dom.mainTabEditor,
    panel: dom.mainPanelEditor,
    isActive: !useActivation,
  });
  setTabUi({
    button: dom.mainTabActivation,
    panel: dom.mainPanelActivation,
    isActive: useActivation,
  });
}

export function wireMainTabEvents() {
  if (dom.mainTabEditor) {
    dom.mainTabEditor.addEventListener("click", () => {
      setActiveMainTab(MAIN_TAB_EDITOR);
    });
  }
  if (dom.mainTabActivation) {
    dom.mainTabActivation.addEventListener("click", () => {
      setActiveMainTab(MAIN_TAB_ACTIVATION);
    });
  }
}
