// "system" removes the attribute so the prefers-color-scheme rule in theme.css applies.
export function applyTheme(root, theme) {
  if (theme === "light" || theme === "dark") root.setAttribute("data-theme", theme);
  else root.removeAttribute("data-theme");
}
