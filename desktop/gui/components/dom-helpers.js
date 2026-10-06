export function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

export function button(className, label, onClick) {
  const node = element("button", className, label);
  node.type = "button";
  node.addEventListener("click", onClick);
  return node;
}

// A label wrapping its control, so no ids are needed to associate them.
export function field(labelText, control) {
  const label = element("label", "ad-field");
  label.appendChild(element("span", "ad-field-label", labelText));
  label.appendChild(control);
  return label;
}
