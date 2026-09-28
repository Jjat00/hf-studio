# Revisión adversarial del árbol sin commit sobre `439ffdb`

Fecha: 2026-09-28. Alcance: todo el diff sin commit que corrige los fallos del primer CI ([run 36496814782](https://github.com/Jjat00/hf-studio/actions/runs/36496814782)): flujo de CI, arranque, pruebas y documentación. No conecté agentes, generé contenido ni arranqué servidores en los puertos 8787 o 3000. No toqué `web/.next` ni modifiqué código.

## Hallazgos

1. **macOS, prioridad media: `ffmpeg-full` instalado puede quedar detrás de otro `ffmpeg` en `PATH`.** En `src/hf_studio/launcher.py:26-31`, la función solo antepone el directorio de Homebrew si este *no aparece* en `PATH`. Si aparece después de `/opt/homebrew/bin`, `/usr/local/bin` u otro directorio con un `ffmpeg` sin `rubberband`, no cambia el orden. Después, `shutil.which("ffmpeg")` elige el primer binario, y los efectos `deep`, `monster` y `ghost` fallan aunque `ffmpeg-full` esté instalado. Reproduje el caso con dos ejecutables temporales: `PATH=regular:full`, `BREW_FFMPEG_FULL=(full,)`; `check_ffmpeg()` conservó `regular/ffmpeg` y emitió «brew install ffmpeg-full». Es una instrucción inútil para quien ya lo instaló. El test nuevo en `tests/test_launcher.py:143-156` solo cubre el directorio ausente de `PATH` y reemplaza `shutil.which` por una función que siempre devuelve `/usr/bin/...`, así que no detecta la selección real. Se debe mover el directorio encontrado al principio aun cuando ya figure en `PATH`, y probar también ese orden con resolución real de `ffmpeg` y `ffprobe`.

## Comprobaciones

- **Fallo original confirmado:** el run 36496814782 tuvo verde en Linux y Windows, y falló en web por `TS2304: Cannot find name 'RouteContext'` y en macOS por `No such filter: 'rubberband'` (`gh run view --log-failed`).
- **Web:** `pnpm exec next typegen` antes de `tsc --noEmit` coincide con la [secuencia que documenta Next.js](https://nextjs.org/docs/app/api-reference/cli/next#next-typegen-options). En una copia aislada de `web/`, sin `.next` y con las dependencias instaladas reutilizadas mediante enlace, ambos comandos terminaron correctamente. El cambio en CI y en los README y `AGENTS.md` es coherente. No usé el `.next` del dueño.
- **macOS en CI:** [Homebrew](https://formulae.brew.sh/formula/ffmpeg-full) ofrece `ffmpeg-full`, incluye `rubberband`, trae `ffmpeg` y `ffprobe`, y lo marca como keg-only. [GitHub Actions](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands#adding-a-system-path) antepone a los pasos siguientes el directorio escrito en `GITHUB_PATH`. La línea nueva del CI debería hacer que las pruebas invoquen ese binario. El fallo descrito arriba afecta al arranque local cuando `PATH` ya contiene el directorio en una posición posterior.
- **Linux y Windows:** el `ffmpeg` local de Linux anuncia el filtro `rubberband`; la suite lo ejercitó. El CI de Windows mantiene `choco install ffmpeg`, que instala la variante *essentials* de Gyan; la [lista del proveedor](https://www.gyan.dev/ffmpeg/builds/#libraries) incluye `librubberband` en esa variante. El `winget install ffmpeg` documentado corresponde a la variante *full* según la misma fuente. La comprobación de arranque no cambia el `PATH` fuera de macOS.
- **Pruebas pedidas:** `.venv/bin/pytest -q`: **155 passed, 2 skipped**. `.venv/bin/ruff check src tests`: **All checks passed**. `git diff --check`: sin errores.
- No ejecuté un nuevo CI ni repetí las pruebas de forma nativa en macOS o Windows con este diff. La comprobación de esas plataformas se basa en el código, el run original y las fuentes de los paquetes.

## Veredicto

**CAMBIOS REQUERIDOS.** Las dos correcciones del CI son adecuadas, pero la preferencia prometida por `ffmpeg-full` en el arranque local de macOS falla con un `PATH` válido y deja inoperantes tres efectos de voz pese a tener el requisito instalado.
