# Con un Café

Mi prensa matinal interactiva. Cada mañana reúne noticias de España, el mundo, economía, política y moda de fuentes abiertas, las agrupa y las ordena por importancia. Con sección International en inglés, podcasts, notas, favoritos y leídas.

## Cómo funciona

- **Cada mañana** (05:15 en invierno, 06:15 en verano, hora de Madrid) GitHub ejecuta `scripts/build.py`. Ese programa lee los titulares de las fuentes de `feeds.json` por RSS, agrupa las noticias que cuentan lo mismo y guarda la edición en `data/`. **No usa IA ni claves y es gratis.**
- **La web** (`index.html`) carga la edición más reciente. Tus notas, favoritos, leídas y sellos se guardan solo en tu navegador.
- **«Profundiza con Claude»** abre Claude con la noticia y sus fuentes. Solo gasta tu uso de Claude cuando lo pulsas.

## Añadir o quitar fuentes

Edita `feeds.json` desde GitHub (icono del lápiz). Cada fuente tiene `name`, `url` (su RSS), `sec` (sección) y `lang` (`es` o `en`).

## Activar la web (una sola vez)

1. **Settings → Pages → Build and deployment → Source:** elige **GitHub Actions**.
2. **Actions → Edición diaria → Run workflow** para crear la primera edición.
3. Tu web estará en `https://stzu123.github.io/Con-un-caf-/`.
