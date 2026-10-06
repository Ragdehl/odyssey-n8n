/** Shared presentation-only line icons for Odyssey actions and primary navigation. */
const ACTION_ICONS = Object.freeze({
  chat: ["M21 12a8 8 0 0 1-8 8H7l-4 2 1.3-4.2A8 8 0 1 1 21 12Z"],
  notes: ["M6 3h9l3 3v15H6z", "M14 3v5h4", "M9 12h6M9 16h6"],
  calendar: ["M5 5h14v14H5z", "M8 3v4M16 3v4M5 9h14", "M9 13h2v2H9z"],
  edit: ["M4 20l4.5-1 10-10-3.5-3.5-10 10L4 20Z", "m13.5-15.5 3.5 3.5"],
  delete: ["M5 7h14", "M9 7V4h6v3", "M8 10v8M12 10v8M16 10v8", "M6 7l1 14h10l1-14"],
  add: ["M12 5v14M5 12h14"],
  play: ["M8 5v14l11-7L8 5Z"],
  stop: ["M7 7h10v10H7z"],
  clock: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z", "M12 7v5l3 2"],
  chevronUp: ["m7 14 5-5 5 5"],
  chevronDown: ["m7 10 5 5 5-5"],
  check: ["m5 12 4 4L19 6"],
  close: ["M7 7l10 10M17 7 7 17"],
  more: ["M5 12h.01M12 12h.01M19 12h.01"],
  openNote: ["M6 3h9l3 3v15H6z", "M14 3v5h4", "M10 15h7", "m14 12 3 3-3 3"],
});

export function actionIcon(name) {
  const paths = ACTION_ICONS[name] ?? ACTION_ICONS.notes;
  const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  icon.setAttribute("viewBox", "0 0 24 24");
  icon.setAttribute("aria-hidden", "true");
  icon.setAttribute("focusable", "false");
  for (const pathData of paths) {
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", pathData);
    icon.append(path);
  }
  return icon;
}

export function setActionIcon(control, name, label) {
  control.replaceChildren(actionIcon(name));
  control.setAttribute("aria-label", label);
  control.setAttribute("title", label);
  return control;
}

export function actionButton(name, label, action, classes = "") {
  const control = document.createElement("button");
  control.type = "button";
  control.className = `icon-action ${classes}`.trim();
  setActionIcon(control, name, label);
  control.addEventListener("click", action);
  return control;
}
