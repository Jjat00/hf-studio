/** Casos de uso: qué se puede hacer con HF Studio, desde la UI y desde el MCP, con mini tutorial y prompts. */
import { l, type L } from "./i18n";

export type Channel = "ui" | "mcp";

export type Step = { title: L; body?: L; tool?: string };

export type Category = "Cinematic" | "Product" | "Animate" | "Motion" | "Edit" | "Social" | "Agents";

export type UseCase = {
  slug: string;
  title: L;
  tagline: L;
  category: Category;
  output: "video" | "image";
  channels: Channel[];
  art: string;
  model: string;
  /** Entrada de ejemplo para cotizar en vivo (el costo se muestra siempre antes de generar). */
  sample: Record<string, unknown>;
  /** Qué cubre el costo de ejemplo cuando el caso tiene varias etapas. */
  costNote?: L;
  /** Estudio de la UI (sin el prompt): `?prompt=` se añade al usar un ejemplo. */
  uiHref?: string;
  preset?: string;
  ui?: Step[];
  /** Lo que le pides a tu agente, en lenguaje natural. */
  ask: L;
  mcp: Step[];
  /** Los prompts van en inglés en ambos idiomas: es lo que entra al modelo. */
  prompts: { label: L; text: string }[];
  tips: L[];
};

const studioHref = (path: "video" | "image", tab: string, mode: string, model: string) =>
  `/${path}?${new URLSearchParams({ tab, mode, model })}`;

export const USE_CASES: UseCase[] = [
  {
    slug: "establishing-shot",
    title: l("Plano de apertura cinematográfico", "Cinematic establishing shot"),
    tagline: l("Abre tu película, reel o landing con un plano amplio de cualquier lugar.", "Open your film, reel or landing page with a sweeping shot of any place."),
    category: "Cinematic",
    output: "video",
    channels: ["ui", "mcp"],
    art: "/art/use-cases/establishing.webp",
    model: "bytedance/seedance-2.0/text-to-video",
    sample: { prompt: "cost preview", duration: 5, resolution: "480p", aspect_ratio: "21:9", generate_audio: true },
    uiHref: studioHref("video", "create", "text", "bytedance/seedance-2.0/text-to-video"),
    preset: "cinematic-establishing",
    ui: [
      { title: l("Abre Video › Texto", "Open Video › Text"), body: l("Seedance 2.0 viene seleccionado. Si quieres otro modelo, elígelo en el selector de modelo.", "Seedance 2.0 is selected by default. Pick another model from the model chip if you want.") },
      { title: l("Escribe el plano", "Write the shot"), body: l("Lugar + hora del día + movimiento de cámara + lente. Basta una frase; pega uno de los prompts de abajo.", "Place + time of day + camera move + lens. One sentence is enough; paste one of the prompts below.") },
      { title: l("Elige formato y duración", "Set format and length"), body: l("21:9 o 16:9 para cine, 9:16 para reels. Empieza con 5 s a 480p mientras iteras.", "21:9 or 16:9 for film, 9:16 for reels. Start with 5 s at 480p while you iterate.") },
      { title: l("Mira el costo y pulsa Generar", "Check the cost, then Generate"), body: l("El precio se actualiza al cambiar los ajustes. No se gasta nada hasta que pulsas Generar.", "The price updates as you change settings. Nothing is spent until you press Generate.") },
      { title: l("Itera", "Iterate"), body: l("Desde la Biblioteca, reutiliza la generación, ajusta la línea de cámara y sube a 720p o 1080p.", "From the Library, Reuse the generation, tweak the camera line and upscale to 720p or 1080p.") },
    ],
    ask: l(
      "Hazme un plano de apertura de 5 segundos en 21:9 de un pueblo pesquero con niebla al amanecer. Muéstrame primero el costo.",
      "Make me a 5 second 21:9 establishing shot of a foggy fishing village at dawn. Show me the cost first.",
    ),
    mcp: [
      { title: l("Busca la receta", "Find the recipe"), body: l("El agente lista las recetas listas y elige la de plano de apertura.", "The agent lists ready-made recipes and picks the establishing-shot one."), tool: "list_presets" },
      { title: l("Cotiza", "Quote it"), body: l("Ejecuta el preset con dry_run y te muestra los créditos y los USD.", "Runs the preset with dry_run and shows you the credits and USD."), tool: "run_preset" },
      { title: l("Genera con tu OK", "Generate on your OK"), body: l("La misma llamada con dry_run: false, el quote_id de la cotización (prueba de que viste el precio) y una clave de idempotencia, para que nunca cobre dos veces.", "Same call with dry_run: false, the quote_id from the quote (proof you saw the price) and an idempotency key, so it never charges twice."), tool: "run_preset" },
      { title: l("Espera y descarga", "Wait and download"), body: l("Espera con long-poll hasta que termina y guarda el MP4 en tu proyecto.", "Long-polls until it finishes and saves the MP4 to your project."), tool: "get_generation → download_outputs" },
    ],
    prompts: [
      { label: l("Pueblo pesquero", "Fishing village"), text: "Cinematic establishing shot of a foggy fishing village at dawn, slow aerial push-in, anamorphic lens, natural film grain, warm window lights through the mist" },
      { label: l("Carretera en el desierto", "Desert highway"), text: "Wide establishing shot of an empty desert highway at golden hour, lateral tracking shot, heat haze, long shadows, 35mm film look" },
      { label: l("Ciudad de neón", "Neon city"), text: "Crane up reveal over a rainy neon city at night, reflections on wet streets, volumetric haze, cinematic blue and magenta palette" },
    ],
    tips: [
      l("Nombra el movimiento de cámara explícitamente: push-in, crane up, lateral tracking.", "Name the camera move explicitly: push-in, crane up, lateral tracking."),
      l("En Seedance el audio viene activado: apágalo si solo necesitas la imagen.", "Audio is on by default in Seedance: turn it off if you only need the picture."),
    ],
  },
  {
    slug: "product-launch",
    title: l("Pack de lanzamiento de producto", "Product launch pack"),
    tagline: l("Una foto hero de estudio de tu producto y luego el mismo plano como video giratorio 360°.", "A studio hero shot of your product, then the same shot as a 360° turntable video."),
    category: "Product",
    output: "image",
    channels: ["ui", "mcp"],
    art: "/art/use-cases/product-launch.webp",
    model: "higgsfield-ai/soul/v2/standard",
    sample: { prompt: "cost preview", aspect_ratio: "4:3", resolution: "1080p" },
    costNote: l("Solo la imagen hero. El video 360° se cotiza aparte, antes de generarlo.", "Hero image only. The 360° video is quoted separately, before you generate it."),
    uiHref: studioHref("image", "create", "text", "higgsfield-ai/soul/v2/standard"),
    preset: "hero-shot",
    ui: [
      { title: l("Escribe la imagen hero", "Write the hero image"), body: l("Imagen › Texto a imagen con Soul 2.0. Describe el producto, la superficie y la luz.", "Image › Text to image with Soul 2.0. Describe the product, the surface and the light.") },
      { title: l("Mira el costo y genera", "Check the cost, then generate"), body: l("Las imágenes cuestan céntimos. Genera 2 o 3 variantes y quédate con la de reflejos más limpios.", "Images cost cents. Generate 2–3 variants and keep the one with the cleanest reflections.") },
      { title: l("Prepara el video", "Set up the video"), body: l("Abre el preset Órbita 360 de producto y suelta la imagen. Se abre a 720p: cambia a 480p para una primera prueba más barata.", "Open the preset Product 360 orbit and drop the image in. It opens at 720p: switch to 480p for a cheaper first test.") },
      { title: l("Mira el costo del video y genera", "Check the video cost, then generate"), body: l("El video es la parte cara. Su precio se muestra antes de pulsar Generar.", "The video is the expensive part. Its price is shown before you press Generate.") },
      { title: l("Exporta", "Export"), body: l("Descarga los dos desde la Biblioteca para la landing y el anuncio.", "Download both from the Library for the landing page and the ad.") },
    ],
    ask: l(
      "Crea una foto hero de unos auriculares inalámbricos negro mate sobre cemento pulido y luego anímala como video en órbita 360. Cotiza los dos pasos antes de generar.",
      "Create a hero shot of matte black wireless headphones on polished concrete, then animate it as a 360 orbit video. Quote both steps before generating.",
    ),
    mcp: [
      { title: l("Cotiza la imagen", "Quote the image"), body: l("Ejecuta el preset hero-shot con dry_run.", "Runs the hero-shot preset with dry_run."), tool: "run_preset" },
      { title: l("Genera y espera", "Generate and wait"), body: l("Genera la imagen y espera a tener la URL.", "Generates the image and waits for the URL."), tool: "run_preset → get_generation" },
      { title: l("Cotiza el video", "Quote the video"), body: l("Usa la URL resultante como foto para product-orbit y te muestra el precio.", "Uses the output URL as photo for product-orbit and shows you the price."), tool: "run_preset (product-orbit, dry_run)" },
      { title: l("Genera con tu OK", "Generate it on your OK"), tool: "run_preset → get_generation" },
      { title: l("Guarda los archivos", "Save the files"), body: l("Descarga el PNG y el MP4 en la carpeta public de tu repo.", "Downloads the PNG and the MP4 into your repo's public folder."), tool: "download_outputs" },
    ],
    prompts: [
      { label: l("Auriculares", "Headphones"), text: "Premium studio hero shot of matte black wireless headphones on polished concrete, soft key light with a crisp rim light, shallow depth of field, clean negative space, commercial product photography, 85mm" },
      { label: l("Perfume", "Perfume"), text: "Luxury perfume bottle on white marble, morning light through a window, soft caustics, minimal composition, editorial beauty photography" },
      { label: l("Zapatilla", "Sneaker"), text: "Single white sneaker floating above reflective black glass, dramatic top light, dust particles, high-end sportswear campaign" },
    ],
    tips: [
      l("Deja espacio vacío si encima irá un titular.", "Leave negative space if a headline will go on top."),
      l("En el video, que el prompt de movimiento hable de la cámara, no del producto.", "For the video keep the motion prompt about the camera, not the product."),
    ],
  },
  {
    slug: "portrait-alive",
    title: l("Dale vida a una foto", "Bring a photo to life"),
    tagline: l("Movimiento sutil y natural para un retrato o una foto fija: respiración, pelo, luz.", "Subtle, natural motion for a portrait or a still: breathing, hair, light."),
    category: "Animate",
    output: "video",
    channels: ["ui", "mcp"],
    art: "/art/use-cases/portrait-alive.webp",
    model: "bytedance/seedance-2.0/image-to-video",
    sample: { prompt: "cost preview", image_url: "https://example.com/a.png", duration: 5, resolution: "480p", generate_audio: false },
    uiHref: studioHref("video", "create", "frames", "bytedance/seedance-2.0/image-to-video"),
    preset: "photo-to-life",
    ui: [
      { title: l("Abre Video › Inicio y final", "Open Video › Start & End"), body: l("Sube tu foto como fotograma inicial. Deja vacío el final.", "Upload your photo as the start frame. Leave the end frame empty.") },
      { title: l("Describe solo el movimiento", "Describe only the motion"), body: l("Qué se mueve y qué poco: pelo, ojos, tela, luz. La cámara casi quieta.", "What moves and how little: hair, eyes, fabric, light. Keep the camera almost still.") },
      { title: l("480p, 5 s, sin audio", "480p, 5 s, audio off"), body: l("La combinación más barata para probar si el movimiento se ve bien.", "The cheapest combination to test whether the motion feels right.") },
      { title: l("Genera", "Generate"), body: l("Mira el costo y genera. Sube la calidad cuando se vea natural.", "Check the cost chip, then generate. Scale up once it looks natural.") },
    ],
    ask: l(
      "Anima ~/Pictures/abuela.jpg con un movimiento sutil y natural, el pelo moviéndose con el viento. 480p, sin audio. Primero el costo.",
      "Animate ~/Pictures/grandma.jpg with subtle natural motion, hair moving in the wind. 480p, no audio. Cost first.",
    ),
    mcp: [
      { title: l("Sube la foto", "Upload the photo"), body: l("Envía el archivo local y obtiene una URL pública.", "Sends the local file and gets a public URL."), tool: "upload_media" },
      { title: l("Cotiza", "Quote"), body: l("Ejecuta photo-to-life con la URL como foto.", "Runs photo-to-life with the URL as photo."), tool: "run_preset (dry_run)" },
      { title: l("Genera y espera", "Generate and wait"), body: l("Con tu OK genera y espera.", "On your OK it generates and waits."), tool: "run_preset → get_generation" },
      { title: l("Descarga", "Download"), body: l("Guarda el MP4 junto a la foto original.", "Saves the MP4 next to the original photo."), tool: "download_outputs" },
    ],
    prompts: [
      { label: l("Retrato", "Portrait"), text: "Subtle natural motion, hair moving in a light breeze, slow blink, gentle smile forming, camera almost still, realistic" },
      { label: l("Paisaje", "Landscape"), text: "Clouds drifting slowly, water shimmering, grass swaying, static camera, peaceful and realistic" },
      { label: l("Foto antigua", "Old photo"), text: "Vintage photograph coming to life, the person turns slightly towards the camera and smiles, film grain preserved, very subtle motion" },
    ],
    tips: [
      l("Menos es más: los movimientos grandes deforman las caras.", "Less is more: big motions distort faces."),
      l("Funcionan mejor las fotos con la cara visible y buena luz.", "Photos with a visible face and good light work best."),
    ],
  },
  {
    slug: "morph",
    title: l("Transición entre dos fotogramas", "Morph between two frames"),
    tagline: l("Una transición continua de una imagen a otra: estaciones, ropa, antes y después.", "A seamless transition from one image to another: seasons, outfits, before and after."),
    category: "Animate",
    output: "video",
    channels: ["ui", "mcp"],
    art: "/art/use-cases/morph.webp",
    model: "bytedance/seedance-2.0/image-to-video",
    sample: { prompt: "cost preview", image_url: "https://example.com/a.png", end_image_url: "https://example.com/b.png", duration: 5, resolution: "480p" },
    uiHref: studioHref("video", "create", "frames", "bytedance/seedance-2.0/image-to-video"),
    preset: "morph",
    ui: [
      { title: l("Prepara dos imágenes", "Prepare two images"), body: l("Mismo encuadre y mismo formato. Genéralas en Imagen si no las tienes.", "Same framing and aspect ratio. Generate them in Image if you don't have them.") },
      { title: l("Abre Video › Inicio y final", "Open Video › Start & End"), body: l("Fotograma inicial = donde empieza, fotograma final = donde termina.", "Start frame = where it begins, End frame = where it lands.") },
      { title: l("Nombra la transición", "Name the transition"), body: l("Fusión suave, la cámara atraviesa, destello de luz o transformación líquida.", "Smooth morph, camera push through, light burst or liquid transformation.") },
      { title: l("Genera a 480p", "Generate at 480p"), body: l("Mira primero el costo; si el recorrido se ve bien, repítelo a 720p.", "Check the cost first; if the path looks right, redo at 720p.") },
    ],
    ask: l(
      "Haz un video de transición de invierno.png a primavera.png con una transición de luz líquida. Muéstrame el precio antes de generar.",
      "Make a morph video from winter.png to spring.png with a liquid light transition. Show me the price before generating.",
    ),
    mcp: [
      { title: l("Sube los dos fotogramas", "Upload both frames"), body: l("Una llamada por archivo.", "One call per file."), tool: "upload_media ×2" },
      { title: l("Cotiza la transición", "Quote the morph"), body: l("Rellena inicio, final y estilo.", "Fills start, end and style."), tool: "run_preset (morph, dry_run)" },
      { title: l("Genera y recoge", "Generate and fetch"), body: l("Genera con tu OK, espera y descarga.", "Generates on your OK, waits and downloads."), tool: "run_preset → get_generation → download_outputs" },
    ],
    prompts: [
      { label: l("Estaciones", "Seasons"), text: "Liquid transformation from the first frame to the last frame, snow melting into spring flowers, continuous shot" },
      { label: l("Antes y después", "Before/after"), text: "Smooth morph from the empty room to the furnished room, camera slowly pushing in, continuous shot" },
      { label: l("Cambio de ropa", "Outfit change"), text: "Light burst transition, the outfit changes from the first frame to the last frame while the pose stays, continuous shot" },
    ],
    tips: [
      l("Cuanto más parecidos los dos encuadres, más limpia la transición.", "The closer the two framings, the cleaner the morph."),
      l("Menciona 'continuous shot' para evitar cortes.", "Mention 'continuous shot' to avoid cuts."),
    ],
  },
  {
    slug: "character-scenes",
    title: l("El mismo personaje, escenas nuevas", "Same character, new scenes"),
    tagline: l("Mantén un personaje coherente entre planos usando imágenes de referencia.", "Keep one character consistent across shots using reference images."),
    category: "Cinematic",
    output: "video",
    channels: ["ui", "mcp"],
    art: "/art/use-cases/character-scenes.webp",
    model: "bytedance/seedance-2.0/reference-to-video",
    sample: { prompt: "cost preview", image_urls: ["https://example.com/a.png"], duration: 5, resolution: "480p", aspect_ratio: "16:9" },
    uiHref: studioHref("video", "create", "references", "bytedance/seedance-2.0/reference-to-video"),
    preset: "character-in-scene",
    ui: [
      { title: l("Abre Video › Referencias", "Open Video › References"), body: l("Añade imágenes de tu personaje en Añadir elementos (hasta 9; suelen bastar 3 o 4 ángulos como frente, perfil y cuerpo entero).", "Add images of your character under Add elements (up to 9; 3–4 angles such as front, side and full body are usually enough).") },
      { title: l("Describe la escena nueva", "Describe the new scene"), body: l("Dónde está, qué hace y cómo se mueve la cámara. No vuelvas a describir su cara.", "Where they are, what they do and how the camera moves. Don't re-describe their face.") },
      { title: l("Genera una escena", "Generate one scene"), body: l("Primero a 480p. Mira el costo.", "480p first. Check the cost chip.") },
      { title: l("Repite para el siguiente plano", "Repeat for the next shot"), body: l("Reutiliza desde la Biblioteca y cambia solo la línea de la escena.", "Reuse from the Library and only change the scene line.") },
    ],
    ask: l(
      "Con las imágenes del personaje en ./refs, haz tres planos de 5 s: mercado de neón de noche, carretera en el desierto y bosque nevado. Cotiza primero todo el lote.",
      "Using the character images in ./refs, make three 5 s shots: neon market at night, desert road, snowy forest. Quote the whole batch first.",
    ),
    mcp: [
      { title: l("Sube las referencias", "Upload the references"), body: l("Una URL por imagen.", "One URL per image."), tool: "upload_media" },
      { title: l("Cotiza el lote", "Quote the batch"), body: l("Tres ítems con las mismas referencias y escenas distintas; devuelve el costo por ítem y el total.", "Three items with the same references and different scenes; returns cost per item and total."), tool: "generate_batch (dry_run)" },
      { title: l("Genera con tu OK", "Generate on your OK"), body: l("El mismo lote con dry_run: false.", "Same batch with dry_run: false."), tool: "generate_batch" },
      { title: l("Espera a todos", "Wait for all"), body: l("Una sola llamada espera los tres y los descarga.", "One call waits for the three and downloads them."), tool: "wait_generations → download_outputs" },
    ],
    prompts: [
      { label: l("Mercado nocturno", "Night market"), text: "The character walks through a neon night market, handheld camera following from behind, then turns to look at the lens" },
      { label: l("Carretera en el desierto", "Desert road"), text: "The character stands by an empty desert road at sunset, wind moving the raincoat, slow push-in" },
      { label: l("Bosque nevado", "Snow forest"), text: "The character walks between snowy pine trees, breath visible, lateral tracking shot, soft blue light" },
    ],
    tips: [
      l("Varios ángulos del mismo personaje valen más que una foto perfecta.", "Several angles of the same character beat one perfect photo."),
      l("Agrupa los planos en un lote para revisar el costo de toda la secuencia de una vez.", "Batch the shots so the whole sequence shares one cost check."),
    ],
  },
  {
    slug: "dance-transfer",
    title: l("Transferir baile y movimiento", "Dance and motion transfer"),
    tagline: l("Tu personaje hace los movimientos de cualquier video de referencia.", "Your character performs the moves of any reference video."),
    category: "Motion",
    output: "video",
    channels: ["ui", "mcp"],
    art: "/art/use-cases/dance-transfer.webp",
    model: "kling-video/v3/motion-control/std",
    sample: { image_url: "https://example.com/a.png", video_url: "https://example.com/a.mp4" },
    uiHref: studioHref("video", "motion", "motion", "kling-video/v3/motion-control/std"),
    preset: "dance-transfer",
    ui: [
      { title: l("Abre Control de movimiento", "Open Motion Control"), body: l("Añade el movimiento a copiar: un clip de 3 a 30 s con el cuerpo entero visible.", "Add the motion to copy: a clip of 3–30 s with the full body visible.") },
      { title: l("Añade tu personaje", "Add your character"), body: l("Una imagen con la cara y el cuerpo visibles, mejor en una pose parecida.", "An image with a visible face and body, ideally in a similar pose.") },
      { title: l("Prompt opcional", "Optional prompt"), body: l("Describe el lugar o la ropa; déjalo vacío para conservar la imagen del personaje.", "Describe the setting or outfit; leave it empty to keep the character's image.") },
      { title: l("El precio aparece al subir", "Price appears after upload"), body: l("Kling cobra por la duración del video, así que el costo se muestra cuando el clip está subido. Confirma y pulsa Generar.", "Kling prices by the video length, so the cost is shown once the clip is in. Confirm, then Generate.") },
    ],
    ask: l(
      "Haz que mi mascota de ./mascota.png haga el baile de ./baile.mp4. Conserva el sonido original. Dime primero el costo.",
      "Make my mascot in ./mascot.png do the dance in ./dance.mp4. Keep the original sound. Tell me the cost first.",
    ),
    mcp: [
      { title: l("Sube los dos archivos", "Upload both files"), body: l("Imagen y video.", "Image and video."), tool: "upload_media ×2" },
      { title: l("Cotiza con la duración del video", "Quote with the video length"), body: l("Ejecuta el preset dance-transfer como dry run con input_video_seconds, así el precio es exacto.", "Runs the dance-transfer preset as a dry run with input_video_seconds, so the price is exact."), tool: "run_preset (dry_run, input_video_seconds)" },
      { title: l("Genera con tu OK", "Generate on your OK"), body: l("La misma llamada con dry_run: false y el quote_id que devolvió.", "Same call with dry_run: false and the quote_id it returned."), tool: "run_preset (quote_id)" },
      { title: l("Espera y descarga", "Wait and download"), tool: "get_generation → download_outputs" },
    ],
    prompts: [
      { label: l("Escenario", "Stage"), text: "On a dark stage with spotlights, smoke on the floor, concert lighting" },
      { label: l("Calle", "Street"), text: "In a sunny street with graffiti walls, keep the outfit from the image" },
      { label: l("Sin prompt", "No prompt"), text: "" },
    ],
    tips: [
      l("Los clips de referencia más cortos cuestan menos: recorta los mejores 5–8 s.", "Shorter reference clips cost less: trim to the best 5–8 s."),
      l("Haz coincidir el formato de la imagen y el del video.", "Match the aspect ratio of the image and the video."),
    ],
  },
  {
    slug: "ad-multiplier",
    title: l("Multiplicador de anuncios", "Ad multiplier"),
    tagline: l("Cambia el producto de un anuncio existente y conserva todo lo demás: un anuncio, muchas variantes.", "Swap the product in an existing ad and keep everything else: one ad, many variants."),
    category: "Product",
    output: "video",
    channels: ["ui", "mcp"],
    art: "/art/use-cases/ad-multiplier.webp",
    model: "higgsfiled/genjutsu/object-swap/v1.0",
    sample: { video_url: "https://example.com/a.mp4", image_urls: ["https://example.com/a.png"], prompt: "cost preview", resolution: "720p" },
    uiHref: studioHref("video", "genjutsu", "swap", "higgsfiled/genjutsu/object-swap/v1.0"),
    preset: "ad-multiplier",
    ui: [
      { title: l("Abre Genjutsu › Cambiar objetos", "Open Genjutsu › Objects swap"), body: l("Sube el anuncio original (4–30 s, al menos 409.600 píxeles por fotograma, p. ej. 640×640).", "Upload the original ad (4–30 s, at least 409,600 pixels per frame, e.g. 640×640).") },
      { title: l("Añade el producto nuevo", "Add the new product"), body: l("Fotos limpias del producto, mejor sobre fondo liso.", "Clean product photos, ideally on a plain background.") },
      { title: l("Di qué reemplazar", "Say what to replace"), body: l("Señala el objeto: 'reemplaza la botella de su mano'.", "Point at the object: 'replace the bottle in her hand'.") },
      { title: l("Mira el costo y genera", "Check the cost and generate"), body: l("Repite con cada producto para tener las variantes.", "Repeat with each product to get the variants.") },
    ],
    ask: l(
      "Toma ./anuncio.mp4 y haz tres versiones cambiando la botella por cada foto de ./botellas. Cotiza el lote y espera mi OK.",
      "Take ./ad.mp4 and make three versions swapping the bottle for each photo in ./bottles. Quote the batch, wait for my OK.",
    ),
    mcp: [
      { title: l("Sube el anuncio y los productos", "Upload the ad and products"), tool: "upload_media" },
      { title: l("Cotiza todas las variantes", "Quote all variants"), body: l("Un ítem por producto; pasa la duración del anuncio para que el total sea completo.", "One item per product; passes the ad's length so the total is complete."), tool: "generate_batch (dry_run, input_video_seconds)" },
      { title: l("Genera y espera", "Generate and wait"), tool: "generate_batch → wait_generations" },
      { title: l("Guárdalo como preset", "Save as a preset"), body: l("Conserva la configuración ganadora para la próxima campaña.", "Keep the winning setup for next campaign."), tool: "save_preset" },
    ],
    prompts: [
      { label: l("Botella", "Bottle"), text: "Replace the bottle in her hand with the product from the image, keep lighting and motion" },
      { label: l("Zapatillas", "Sneakers"), text: "Replace the sneakers on his feet with the new model, same colors of the scene" },
      { label: l("Lata", "Can"), text: "Swap the soda can on the table for the new can, keep reflections and condensation" },
    ],
    tips: [
      l("Sé concreto con el objeto: el modelo conserva todo lo demás.", "Be specific about which object: the model keeps everything else."),
      l("Genjutsu conserva el movimiento y el ritmo originales.", "Genjutsu keeps the original motion and timing."),
    ],
  },
  {
    slug: "restyle",
    title: l("Cambia el estilo de un clip", "Restyle a clip"),
    tagline: l("Reescribe cualquier video con un prompt: anime, plastilina, look de película, del día a la noche.", "Rewrite any video with a prompt: anime, claymation, film look, day to night."),
    category: "Edit",
    output: "video",
    channels: ["ui", "mcp"],
    art: "/art/use-cases/restyle.webp",
    model: "bytedance/seedance-2.5/video-edit",
    sample: { video_url: "https://example.com/a.mp4", prompt: "cost preview" },
    uiHref: studioHref("video", "edit", "edit", "bytedance/seedance-2.5/video-edit"),
    ui: [
      { title: l("Abre Editar video › Editar", "Open Edit Video › Edit"), body: l("Sube el clip o reutiliza una generación anterior desde la Biblioteca.", "Upload the clip, or reuse a previous generation from the Library.") },
      { title: l("Describe el nuevo look", "Describe the new look"), body: l("Estilo + lo que debe quedarse: 'como anime pintado a mano, conserva la cámara y el ritmo'.", "Style + what must stay: 'as a hand painted anime, keep the camera and timing'.") },
      { title: l("El costo es por segundo", "Cost is per second"), body: l("El precio aparece cuando el clip está cargado. Recorta antes los clips largos.", "The price appears once the clip is loaded. Trim long clips first.") },
      { title: l("Genera", "Generate"), body: l("Compáralo con el original en la Biblioteca.", "Compare with the original in the Library.") },
    ],
    ask: l(
      "Cambia el estilo de ./calle.mp4 a una escena de anime pintado a mano y conserva el movimiento de cámara. Cotiza primero con la duración real.",
      "Restyle ./street.mp4 as a hand painted anime scene, keep the camera move. Quote with the real length first.",
    ),
    mcp: [
      { title: l("Sube el clip", "Upload the clip"), tool: "upload_media" },
      { title: l("Cotiza con la duración", "Quote with the length"), tool: "estimate_cost (input_video_seconds)" },
      { title: l("Genera y espera", "Generate and wait"), tool: "generate → get_generation" },
      { title: l("Descarga", "Download"), tool: "download_outputs" },
    ],
    prompts: [
      { label: l("Anime", "Anime"), text: "Restyle the whole video as a hand painted anime illustration, keep the camera motion and timing" },
      { label: l("Del día a la noche", "Day to night"), text: "Turn the scene into a rainy night with neon reflections, keep people and camera unchanged" },
      { label: l("Plastilina", "Claymation"), text: "Transform everything into a stop motion claymation look, visible fingerprints on the clay" },
    ],
    tips: [
      l("Di explícitamente lo que no debe cambiar.", "Say explicitly what must not change."),
      l("Los clips cortos (5–8 s) dan los resultados más coherentes.", "Short clips (5–8 s) give the most consistent results."),
    ],
  },
  {
    slug: "extend",
    title: l("Extiende un plano", "Extend a shot"),
    tagline: l("¿El plano terminó demasiado pronto? Continúalo desde su último fotograma.", "The shot ended too soon? Continue it from its last frame."),
    category: "Edit",
    output: "video",
    channels: ["ui", "mcp"],
    art: "/art/use-cases/extend.webp",
    model: "bytedance/seedance-2.5/video-extend",
    sample: { video_url: "https://example.com/a.mp4", prompt: "cost preview" },
    uiHref: studioHref("video", "edit", "extend", "bytedance/seedance-2.5/video-extend"),
    ui: [
      { title: l("Abre Editar video › Extender", "Open Edit Video › Extend"), body: l("Sube el clip que quieres continuar.", "Upload the clip to continue.") },
      { title: l("Di qué pasa después", "Say what happens next"), body: l("Continúa la acción y la cámara: 'el coche sigue avanzando y la cámara sube'.", "Continue the action and the camera: 'the car keeps driving and the camera rises'.") },
      { title: l("Mira el costo", "Check the cost"), body: l("Y pulsa Generar.", "Then Generate.") },
    ],
    ask: l(
      "Extiende la última generación 5 segundos más: el coche sigue por el acantilado y la cámara sube hasta revelar el mar.",
      "Extend the last generation 5 more seconds: the car keeps driving along the cliff and the camera rises to reveal the sea.",
    ),
    mcp: [
      { title: l("Busca el clip", "Find the clip"), body: l("Toma el último video terminado de tu historial.", "Takes the last completed video from your history."), tool: "list_generations" },
      { title: l("Cotiza la extensión", "Quote the extension"), tool: "estimate_cost" },
      { title: l("Genera y espera", "Generate and wait"), tool: "generate → get_generation" },
    ],
    prompts: [
      { label: l("Revelar", "Reveal"), text: "Continue the shot, the car keeps driving along the cliff road and the camera rises to reveal the sea at sunset" },
      { label: l("Seguir", "Follow"), text: "Continue seamlessly, the character keeps walking and turns the corner, handheld camera follows" },
      { label: l("Final", "Ending"), text: "Continue the shot and slowly pull back into a wide shot, fade the action to a calm ending" },
    ],
    tips: [
      l("Extiende varias veces seguidas para construir planos más largos.", "Extend a few times in a row to build longer shots."),
      l("Mantén las mismas palabras de estilo que el prompt original.", "Keep the same style words as the original prompt."),
    ],
  },
  {
    slug: "reel-covers",
    title: l("Portadas de reels en lote", "Reel covers in batch"),
    tagline: l("Una serie de portadas verticales para redes, con espacio para el titular.", "A set of vertical covers for social media, with room for the headline."),
    category: "Social",
    output: "image",
    channels: ["ui", "mcp"],
    art: "/art/use-cases/reel-covers.webp",
    model: "z-image/turbo",
    sample: { prompt: "cost preview", aspect_ratio: "9:16", resolution: "2k" },
    uiHref: studioHref("image", "create", "text", "z-image/turbo"),
    preset: "reel-cover",
    ui: [
      { title: l("Abre el preset Portada de reel", "Open the Reel cover preset"), body: l("O Imagen › Texto a imagen con un modelo rápido y 9:16.", "Or Image › Text to image with a fast model and 9:16.") },
      { title: l("Tema y ambiente", "Subject and mood"), body: l("Una portada por tema; mantén el mismo ambiente en toda la serie.", "One cover per subject; keep the same mood for the whole series.") },
      { title: l("Genera", "Generate"), body: l("Las imágenes cuestan céntimos: genera varias y elige.", "Images cost cents: generate several and pick.") },
    ],
    ask: l(
      "Haz 6 portadas de reels para mi cafetería, cinematográficas y sombrías, con espacio para un titular. Cotiza el lote.",
      "Make 6 reel covers for my coffee shop, moody cinematic, room for a headline. Quote the batch.",
    ),
    mcp: [
      { title: l("Planifica la serie", "Plan the series"), body: l("El agente escribe seis temas que encajen con tu marca.", "The agent writes six subjects that fit your brand.") },
      { title: l("Cotiza el lote", "Quote the batch"), tool: "generate_batch (dry_run)" },
      { title: l("Genera, espera y descarga", "Generate, wait, download"), body: l("Las seis de una vez en ./covers.", "All six in one go into ./covers."), tool: "generate_batch → wait_generations → download_outputs" },
    ],
    prompts: [
      { label: l("Arte latte", "Latte art"), text: "Vertical social media cover photo of a barista pouring latte art, moody cinematic, strong focal point, generous empty space in the upper third for a headline, no text" },
      { label: l("Chef", "Chef"), text: "Vertical cover photo of a chef plating a dish under a single warm lamp, dark background, space at the top for a title, no text" },
      { label: l("Corredora", "Runner"), text: "Vertical cover photo of a runner at dawn on an empty bridge, retro film look, sky filling the upper third, no text" },
    ],
    tips: [
      l("'no text' evita letras falsas en la imagen.", "'no text' avoids fake letters in the image."),
      l("Mismas palabras de ambiente = una cuadrícula coherente en tu perfil.", "Same mood words = consistent grid on your profile."),
    ],
  },
  {
    slug: "storyboard",
    title: l("Storyboard a partir de un guion", "Storyboard from a script"),
    tagline: l("Tu agente divide un guion en planos y genera un fotograma para cada uno.", "Your agent breaks a script into shots and generates a frame for each one."),
    category: "Agents",
    output: "image",
    channels: ["mcp"],
    art: "/art/use-cases/storyboard.webp",
    model: "higgsfield-ai/soul/v2/standard",
    sample: { prompt: "cost preview", aspect_ratio: "16:9", resolution: "1080p" },
    ask: l(
      "Lee ./guion.md, divídelo en 6 planos y genera un fotograma 16:9 para cada uno con el mismo estilo visual. Cotiza primero el lote y guárdalos en ./storyboard.",
      "Read ./script.md, split it into 6 shots and generate a 16:9 frame for each with the same visual style. Quote the batch first and save them to ./storyboard.",
    ),
    mcp: [
      { title: l("Lee el guion", "Read the script"), body: l("El agente lee el archivo y escribe una descripción de plano por momento (tamaño de plano, acción, luz).", "The agent reads the file and writes one shot description per beat (shot size, action, light).") },
      { title: l("Elige un modelo", "Pick a model"), body: l("Pide el mejor modelo de texto a imagen para fotogramas de película coherentes.", "Asks for the best text-to-image model for consistent film stills."), tool: "recommend_models" },
      { title: l("Cotiza todos los fotogramas", "Quote all frames"), body: l("Un ítem del lote por plano, con el mismo sufijo de estilo.", "One batch item per shot, same style suffix."), tool: "generate_batch (dry_run)" },
      { title: l("Genera y recoge", "Generate and collect"), body: l("Espera a todos y guarda shot-01.png … shot-06.png.", "Waits for all and saves shot-01.png … shot-06.png."), tool: "wait_generations → download_outputs" },
      { title: l("Anima los mejores", "Animate the keepers"), body: l("Opcional: convierte los fotogramas elegidos en clips de 5 s con imagen a video, cotizados otra vez.", "Optional: turns chosen frames into 5 s clips with image-to-video, quoted again.") },
    ],
    prompts: [
      { label: l("Sufijo de estilo", "Style suffix"), text: "cinematic film still, anamorphic, muted teal and orange palette, 35mm grain" },
      { label: l("Línea de plano", "Shot line"), text: "Wide shot: an astronaut crosses a red desert plain at dusk, tiny against the landscape" },
      { label: l("Primer plano", "Close-up"), text: "Extreme close-up: a glowing blue flower reflected in the astronaut's visor" },
    ],
    tips: [
      l("Dale al agente un único sufijo de estilo para todos los fotogramas.", "Give the agent one shared style suffix for all frames."),
      l("Pide tamaños de plano (general, medio, primer plano) para lograr el ritmo de un storyboard real.", "Ask for shot sizes (wide, medium, close-up) to get a real storyboard rhythm."),
    ],
  },
  {
    slug: "agent-assets",
    title: l("Recursos para tu código", "Assets for your codebase"),
    tagline: l("Mientras programas, tu agente genera las imágenes que necesita una página y las deja en el repo.", "While coding, your agent generates the images a page needs and drops them into the repo."),
    category: "Agents",
    output: "image",
    channels: ["mcp"],
    art: "/art/use-cases/agent-assets.webp",
    model: "higgsfield-ai/soul/v2/standard",
    sample: { prompt: "cost preview", aspect_ratio: "16:9", resolution: "1080p" },
    ask: l(
      "Esta landing necesita una imagen hero y tres ilustraciones de funcionalidades. Genéralas con nuestro estilo, cotiza primero, guárdalas en public/art como WebP y conéctalas a la página.",
      "This landing page needs a hero image and three feature illustrations. Generate them in our style, quote first, save to public/art as WebP and wire them into the page.",
    ),
    mcp: [
      { title: l("Lee la página", "Read the page"), body: l("El agente mira los componentes para ver qué imágenes faltan y sus proporciones.", "The agent looks at the components to see which images are missing and their aspect ratios.") },
      { title: l("Cotiza el conjunto", "Quote the set"), tool: "generate_batch (dry_run)" },
      { title: l("Genera con tu OK", "Generate on your OK"), tool: "generate_batch → wait_generations" },
      { title: l("Guárdalas en el repo", "Save into the repo"), body: l("Descarga en public/art, convierte a WebP y edita el JSX para usarlas.", "Downloads to public/art, converts to WebP and edits the JSX to use them."), tool: "download_outputs" },
      { title: l("Reutiliza la receta", "Reuse the recipe"), body: l("Guarda el estilo como preset para la próxima página.", "Saves the style as a preset for the next page."), tool: "save_preset" },
    ],
    prompts: [
      { label: l("Hero", "Hero"), text: "Wide hero image for a coffee shop website, warm morning light over the counter, shallow depth of field, space on the left for a headline" },
      { label: l("Funcionalidad", "Feature"), text: "Minimal still life of coffee beans and a ceramic cup on linen, top light, soft shadows, square crop" },
      { label: l("Equipo", "Team"), text: "Candid photo of two baristas laughing behind the counter, natural light, editorial style" },
    ],
    tips: [
      l("Dile al agente los tamaños exactos que espera el diseño.", "Tell the agent the exact sizes the layout expects."),
      l("Los resultados se copian en local, así que los enlaces nunca caducan.", "Outputs are copied locally, so links never expire."),
    ],
  },
];

export const CATEGORIES: Category[] = [...new Set(USE_CASES.map((u) => u.category))];
