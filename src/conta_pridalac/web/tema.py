"""Paleta corporativa para la interfaz web (tema claro y oscuro).

Los valores son los de `empresa_theme.py` (las demás aplicaciones de escritorio de la empresa): mismos nombres y mismos colores, para que
todas las aplicaciones tengan el mismo aspecto. Se publican como variables CSS (`--bg-base`, `--pistacho`…) y el selector de tema
(automático, claro u oscuro) sólo cambia el atributo `data-theme` de la página.
"""
from __future__ import annotations

DARK: dict[str, str] = {
    "bg_base": "#1E2124",
    "bg_panel": "#252930",
    "bg_elevated": "#2E3440",
    "border": "#3A4150",
    "border_focus": "#8DB84A",
    "pistacho": "#8DB84A",
    "pistacho_hover": "#A0CC58",
    "pistacho_muted": "#6A9438",
    "pistacho_pale": "#C8DFA0",
    "text_primary": "#E8E4D8",
    "text_secondary": "#9A9888",
    "text_disabled": "#5A5A52",
    "danger": "#D95B5B",
    "danger_bg": "#3A2020",
    "warning": "#D4903A",
    "warning_bg": "#3A2E10",
    "info": "#5A9BCC",
    "info_bg": "#1A2E3A",
    "success": "#8DB84A",
    "success_bg": "#1E2E10",
    "selection_bg": "#8DB84A",
    "selection_fg": "#1E2124",
}

LIGHT: dict[str, str] = {
    "bg_base": "#F5F4F0",
    "bg_panel": "#FFFFFF",
    "bg_elevated": "#EDF0E8",
    "border": "#D0D4C8",
    "border_focus": "#5A8A1A",
    "pistacho": "#5A8A1A",
    "pistacho_hover": "#4A7A10",
    "pistacho_muted": "#3A6A0A",
    "pistacho_pale": "#8DB84A",
    "text_primary": "#1A1F14",
    "text_secondary": "#6A7060",
    "text_disabled": "#A8B098",
    "danger": "#C03030",
    "danger_bg": "#FDF0F0",
    "warning": "#B06020",
    "warning_bg": "#FDF5E8",
    "info": "#2A6A9A",
    "info_bg": "#EEF5FC",
    "success": "#5A8A1A",
    "success_bg": "#EFF5E8",
    "selection_bg": "#5A8A1A",
    "selection_fg": "#FFFFFF",
}


def _variables(paleta: dict[str, str]) -> str:
    return "\n".join(f"  --{clave.replace('_', '-')}: {valor};" for clave, valor in paleta.items())


def css_de_tema() -> str:
    """Variables CSS de los dos temas. `data-theme="auto"` (o sin atributo) sigue la preferencia del sistema."""
    return (
        f":root[data-theme='dark'] {{\n  color-scheme: dark;\n{_variables(DARK)}\n}}\n"
        f":root[data-theme='light'] {{\n  color-scheme: light;\n{_variables(LIGHT)}\n}}\n"
        f":root:not([data-theme='light']):not([data-theme='dark']) {{\n  color-scheme: light;\n{_variables(LIGHT)}\n}}\n"
        f"@media (prefers-color-scheme: dark) {{\n  :root:not([data-theme='light']):not([data-theme='dark']) {{\n    color-scheme: dark;\n{_variables(DARK)}\n  }}\n}}\n"
    )
