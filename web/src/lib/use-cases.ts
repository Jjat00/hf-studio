/** Casos de uso: qué se puede hacer con HF Studio, desde la UI y desde el MCP, con mini tutorial y prompts. */

export type Channel = "ui" | "mcp";

export type Step = { title: string; body: string; tool?: string };

export type UseCase = {
  slug: string;
  title: string;
  tagline: string;
  category: "Cinematic" | "Product" | "Animate" | "Motion" | "Edit" | "Social" | "Agents";
  output: "video" | "image";
  channels: Channel[];
  art: string;
  model: string;
  /** Entrada de ejemplo para cotizar en vivo (el costo se muestra siempre antes de generar). */
  sample: Record<string, unknown>;
  /** Estudio de la UI (sin el prompt): `?prompt=` se añade al usar un ejemplo. */
  uiHref?: string;
  preset?: string;
  ui?: Step[];
  /** Lo que le pides a tu agente, en lenguaje natural. */
  ask: string;
  mcp: Step[];
  prompts: { label: string; text: string }[];
  tips: string[];
};

const studioHref = (path: "video" | "image", tab: string, mode: string, model: string) =>
  `/${path}?${new URLSearchParams({ tab, mode, model })}`;

export const USE_CASES: UseCase[] = [
  {
    slug: "establishing-shot",
    title: "Cinematic establishing shot",
    tagline: "Open your film, reel or landing page with a sweeping shot of any place.",
    category: "Cinematic",
    output: "video",
    channels: ["ui", "mcp"],
    art: "/art/use-cases/establishing.webp",
    model: "bytedance/seedance-2.0/text-to-video",
    sample: { prompt: "cost preview", duration: 5, resolution: "480p", aspect_ratio: "21:9", generate_audio: true },
    uiHref: studioHref("video", "create", "text", "bytedance/seedance-2.0/text-to-video"),
    preset: "cinematic-establishing",
    ui: [
      { title: "Open Video › Text", body: "Seedance 2.0 is selected by default. Pick another model from the model chip if you want." },
      { title: "Write the shot", body: "Place + time of day + camera move + lens. One sentence is enough; paste one of the prompts below." },
      { title: "Set format and length", body: "21:9 or 16:9 for film, 9:16 for reels. Start with 5 s at 480p while you iterate." },
      { title: "Check the cost, then Generate", body: "The price updates as you change settings. Nothing is spent until you press Generate." },
      { title: "Iterate", body: "From the Library, Reuse the generation, tweak the camera line and upscale to 720p or 1080p." },
    ],
    ask: "Make me a 5 second 21:9 establishing shot of a foggy fishing village at dawn. Show me the cost first.",
    mcp: [
      { title: "Find the recipe", body: "The agent lists ready-made recipes and picks the establishing-shot one.", tool: "list_presets" },
      { title: "Quote it", body: "Runs the preset with dry_run and shows you the credits and USD.", tool: "run_preset" },
      { title: "Generate on your OK", body: "Same call with dry_run: false and an idempotency key, so it never charges twice.", tool: "run_preset" },
      { title: "Wait and download", body: "Long-polls until it finishes and saves the MP4 to your project.", tool: "get_generation → download_outputs" },
    ],
    prompts: [
      { label: "Fishing village", text: "Cinematic establishing shot of a foggy fishing village at dawn, slow aerial push-in, anamorphic lens, natural film grain, warm window lights through the mist" },
      { label: "Desert highway", text: "Wide establishing shot of an empty desert highway at golden hour, lateral tracking shot, heat haze, long shadows, 35mm film look" },
      { label: "Neon city", text: "Crane up reveal over a rainy neon city at night, reflections on wet streets, volumetric haze, cinematic blue and magenta palette" },
    ],
    tips: ["Name the camera move explicitly: push-in, crane up, lateral tracking.", "Audio is on by default in Seedance: turn it off if you only need the picture."],
  },
  {
    slug: "product-launch",
    title: "Product launch pack",
    tagline: "A studio hero shot of your product, then the same shot as a 360° turntable video.",
    category: "Product",
    output: "image",
    channels: ["ui", "mcp"],
    art: "/art/use-cases/product-launch.webp",
    model: "higgsfield-ai/soul/v2/standard",
    sample: { prompt: "cost preview", aspect_ratio: "4:3", resolution: "1080p" },
    uiHref: studioHref("image", "create", "text", "higgsfield-ai/soul/v2/standard"),
    preset: "hero-shot",
    ui: [
      { title: "Generate the hero image", body: "Image › Text to image with Soul 2.0. Describe the product, the surface and the light." },
      { title: "Pick the best frame", body: "Generate 2–3 variants and keep the one with the cleanest reflections." },
      { title: "Animate it", body: "Open the preset Product 360 orbit and drop the image in; or Video › Start & End with the image as start frame." },
      { title: "Check both costs", body: "The image costs cents; the 5 s video at 480p is the expensive part. Confirm before generating." },
      { title: "Export", body: "Download both from the Library for the landing page and the ad." },
    ],
    ask: "Create a hero shot of matte black wireless headphones on polished concrete, then animate it as a 360 orbit video. Quote both steps before generating.",
    mcp: [
      { title: "Quote the image", body: "Runs the hero-shot preset with dry_run.", tool: "run_preset" },
      { title: "Generate and wait", body: "Generates the image and waits for the URL.", tool: "run_preset → get_generation" },
      { title: "Chain into video", body: "Uses the output URL as photo for product-orbit, quoted first.", tool: "run_preset (product-orbit)" },
      { title: "Save the files", body: "Downloads the PNG and the MP4 into your repo's public folder.", tool: "download_outputs" },
    ],
    prompts: [
      { label: "Headphones", text: "Premium studio hero shot of matte black wireless headphones on polished concrete, soft key light with a crisp rim light, shallow depth of field, clean negative space, commercial product photography, 85mm" },
      { label: "Perfume", text: "Luxury perfume bottle on white marble, morning light through a window, soft caustics, minimal composition, editorial beauty photography" },
      { label: "Sneaker", text: "Single white sneaker floating above reflective black glass, dramatic top light, dust particles, high-end sportswear campaign" },
    ],
    tips: ["Leave negative space if a headline will go on top.", "For the video keep the motion prompt about the camera, not the product."],
  },
  {
    slug: "portrait-alive",
    title: "Bring a photo to life",
    tagline: "Subtle, natural motion for a portrait or a still: breathing, hair, light.",
    category: "Animate",
    output: "video",
    channels: ["ui", "mcp"],
    art: "/art/use-cases/portrait-alive.webp",
    model: "bytedance/seedance-2.0/image-to-video",
    sample: { prompt: "cost preview", image_url: "https://example.com/a.png", duration: 5, resolution: "480p", generate_audio: false },
    uiHref: studioHref("video", "create", "frames", "bytedance/seedance-2.0/image-to-video"),
    preset: "photo-to-life",
    ui: [
      { title: "Open Video › Start & End", body: "Upload your photo as the start frame. Leave the end frame empty." },
      { title: "Describe only the motion", body: "What moves and how little: hair, eyes, fabric, light. Keep the camera almost still." },
      { title: "480p, 5 s, audio off", body: "The cheapest combination to test whether the motion feels right." },
      { title: "Generate", body: "Check the cost chip, then generate. Scale up once it looks natural." },
    ],
    ask: "Animate ~/Pictures/grandma.jpg with subtle natural motion, hair moving in the wind. 480p, no audio. Cost first.",
    mcp: [
      { title: "Upload the photo", body: "Sends the local file and gets a public URL.", tool: "upload_media" },
      { title: "Quote", body: "Runs photo-to-life with the URL as photo.", tool: "run_preset (dry_run)" },
      { title: "Generate and wait", body: "On your OK it generates and waits.", tool: "run_preset → get_generation" },
      { title: "Download", body: "Saves the MP4 next to the original photo.", tool: "download_outputs" },
    ],
    prompts: [
      { label: "Portrait", text: "Subtle natural motion, hair moving in a light breeze, slow blink, gentle smile forming, camera almost still, realistic" },
      { label: "Landscape", text: "Clouds drifting slowly, water shimmering, grass swaying, static camera, peaceful and realistic" },
      { label: "Old photo", text: "Vintage photograph coming to life, the person turns slightly towards the camera and smiles, film grain preserved, very subtle motion" },
    ],
    tips: ["Less is more: big motions distort faces.", "Photos with a visible face and good light work best."],
  },
  {
    slug: "morph",
    title: "Morph between two frames",
    tagline: "A seamless transition from one image to another: seasons, outfits, before and after.",
    category: "Animate",
    output: "video",
    channels: ["ui", "mcp"],
    art: "/art/use-cases/morph.webp",
    model: "bytedance/seedance-2.0/image-to-video",
    sample: { prompt: "cost preview", image_url: "https://example.com/a.png", end_image_url: "https://example.com/b.png", duration: 5, resolution: "480p" },
    uiHref: studioHref("video", "create", "frames", "bytedance/seedance-2.0/image-to-video"),
    preset: "morph",
    ui: [
      { title: "Prepare two images", body: "Same framing and aspect ratio. Generate them in Image if you don't have them." },
      { title: "Open Video › Start & End", body: "Start frame = where it begins, End frame = where it lands." },
      { title: "Name the transition", body: "Smooth morph, camera push through, light burst or liquid transformation." },
      { title: "Generate at 480p", body: "Check the cost first; if the path looks right, redo at 720p." },
    ],
    ask: "Make a morph video from winter.png to spring.png with a liquid light transition. Show me the price before generating.",
    mcp: [
      { title: "Upload both frames", body: "One call per file.", tool: "upload_media ×2" },
      { title: "Quote the morph", body: "Fills start, end and style.", tool: "run_preset (morph, dry_run)" },
      { title: "Generate and fetch", body: "Generates on your OK, waits and downloads.", tool: "run_preset → get_generation → download_outputs" },
    ],
    prompts: [
      { label: "Seasons", text: "Liquid transformation from the first frame to the last frame, snow melting into spring flowers, continuous shot" },
      { label: "Before/after", text: "Smooth morph from the empty room to the furnished room, camera slowly pushing in, continuous shot" },
      { label: "Outfit change", text: "Light burst transition, the outfit changes from the first frame to the last frame while the pose stays, continuous shot" },
    ],
    tips: ["The closer the two framings, the cleaner the morph.", "Mention 'continuous shot' to avoid cuts."],
  },
  {
    slug: "character-scenes",
    title: "Same character, new scenes",
    tagline: "Keep one character consistent across shots using reference images.",
    category: "Cinematic",
    output: "video",
    channels: ["ui", "mcp"],
    art: "/art/use-cases/character-scenes.webp",
    model: "bytedance/seedance-2.0/reference-to-video",
    sample: { prompt: "cost preview", image_urls: ["https://example.com/a.png"], duration: 5, resolution: "480p", aspect_ratio: "16:9" },
    uiHref: studioHref("video", "create", "references", "bytedance/seedance-2.0/reference-to-video"),
    preset: "character-in-scene",
    ui: [
      { title: "Open Video › References", body: "Add 1–4 images of your character under Add elements (front, side, full body)." },
      { title: "Describe the new scene", body: "Where they are, what they do and how the camera moves. Don't re-describe their face." },
      { title: "Generate one scene", body: "480p first. Check the cost chip." },
      { title: "Repeat for the next shot", body: "Reuse from the Library and only change the scene line." },
    ],
    ask: "Using the character images in ./refs, make three 5 s shots: neon market at night, desert road, snowy forest. Quote the whole batch first.",
    mcp: [
      { title: "Upload the references", body: "One URL per image.", tool: "upload_media" },
      { title: "Quote the batch", body: "Three items with the same references and different scenes; returns cost per item and total.", tool: "generate_batch (dry_run)" },
      { title: "Generate on your OK", body: "Same batch with dry_run: false.", tool: "generate_batch" },
      { title: "Wait for all", body: "One call waits for the three and downloads them.", tool: "wait_generations → download_outputs" },
    ],
    prompts: [
      { label: "Night market", text: "The character walks through a neon night market, handheld camera following from behind, then turns to look at the lens" },
      { label: "Desert road", text: "The character stands by an empty desert road at sunset, wind moving the raincoat, slow push-in" },
      { label: "Snow forest", text: "The character walks between snowy pine trees, breath visible, lateral tracking shot, soft blue light" },
    ],
    tips: ["Several angles of the same character beat one perfect photo.", "Batch the shots so the whole sequence shares one cost check."],
  },
  {
    slug: "dance-transfer",
    title: "Dance and motion transfer",
    tagline: "Your character performs the moves of any reference video.",
    category: "Motion",
    output: "video",
    channels: ["ui", "mcp"],
    art: "/art/use-cases/dance-transfer.webp",
    model: "kling-video/v3/motion-control/std",
    sample: { image_url: "https://example.com/a.png", video_url: "https://example.com/a.mp4" },
    uiHref: studioHref("video", "motion", "motion", "kling-video/v3/motion-control/std"),
    preset: "dance-transfer",
    ui: [
      { title: "Open Motion Control", body: "Add the motion to copy: a clip of 3–30 s with the full body visible." },
      { title: "Add your character", body: "An image with a visible face and body, ideally in a similar pose." },
      { title: "Optional prompt", body: "Describe the setting or outfit; leave it empty to keep the character's image." },
      { title: "Price appears after upload", body: "Kling prices by the video length, so the cost is shown once the clip is in. Confirm, then Generate." },
    ],
    ask: "Make my mascot in ./mascot.png do the dance in ./dance.mp4. Keep the original sound. Tell me the cost first.",
    mcp: [
      { title: "Upload both files", body: "Image and video.", tool: "upload_media ×2" },
      { title: "Quote with the video length", body: "The agent passes input_video_seconds so the price is exact.", tool: "estimate_cost" },
      { title: "Generate on your OK", body: "Runs the dance-transfer preset.", tool: "run_preset" },
      { title: "Wait and download", body: "", tool: "get_generation → download_outputs" },
    ],
    prompts: [
      { label: "Stage", text: "On a dark stage with spotlights, smoke on the floor, concert lighting" },
      { label: "Street", text: "In a sunny street with graffiti walls, keep the outfit from the image" },
      { label: "No prompt", text: "" },
    ],
    tips: ["Shorter reference clips cost less: trim to the best 5–8 s.", "Match the aspect ratio of the image and the video."],
  },
  {
    slug: "ad-multiplier",
    title: "Ad multiplier",
    tagline: "Swap the product in an existing ad and keep everything else: one ad, many variants.",
    category: "Product",
    output: "video",
    channels: ["ui", "mcp"],
    art: "/art/use-cases/ad-multiplier.webp",
    model: "higgsfiled/genjutsu/object-swap/v1.0",
    sample: { video_url: "https://example.com/a.mp4", image_urls: ["https://example.com/a.png"], prompt: "cost preview", resolution: "720p" },
    uiHref: studioHref("video", "genjutsu", "swap", "higgsfiled/genjutsu/object-swap/v1.0"),
    preset: "ad-multiplier",
    ui: [
      { title: "Open Genjutsu › Objects swap", body: "Upload the original ad (4–30 s, at least 640×640)." },
      { title: "Add the new product", body: "Clean product photos, ideally on a plain background." },
      { title: "Say what to replace", body: "Point at the object: 'replace the bottle in her hand'." },
      { title: "Check the cost and generate", body: "Repeat with each product to get the variants." },
    ],
    ask: "Take ./ad.mp4 and make three versions swapping the bottle for each photo in ./bottles. Quote the batch, wait for my OK.",
    mcp: [
      { title: "Upload the ad and products", body: "", tool: "upload_media" },
      { title: "Quote all variants", body: "One item per product, total cost first.", tool: "generate_batch (dry_run)" },
      { title: "Generate and wait", body: "", tool: "generate_batch → wait_generations" },
      { title: "Save as a preset", body: "Keep the winning setup for next campaign.", tool: "save_preset" },
    ],
    prompts: [
      { label: "Bottle", text: "Replace the bottle in her hand with the product from the image, keep lighting and motion" },
      { label: "Sneakers", text: "Replace the sneakers on his feet with the new model, same colors of the scene" },
      { label: "Can", text: "Swap the soda can on the table for the new can, keep reflections and condensation" },
    ],
    tips: ["Be specific about which object: the model keeps everything else.", "Genjutsu keeps the original motion and timing."],
  },
  {
    slug: "restyle",
    title: "Restyle a clip",
    tagline: "Rewrite any video with a prompt: anime, claymation, film look, day to night.",
    category: "Edit",
    output: "video",
    channels: ["ui", "mcp"],
    art: "/art/use-cases/restyle.webp",
    model: "bytedance/seedance-2.5/video-edit",
    sample: { video_url: "https://example.com/a.mp4", prompt: "cost preview" },
    uiHref: studioHref("video", "edit", "edit", "bytedance/seedance-2.5/video-edit"),
    ui: [
      { title: "Open Edit Video › Edit", body: "Upload the clip, or reuse a previous generation from the Library." },
      { title: "Describe the new look", body: "Style + what must stay: 'as a hand painted anime, keep the camera and timing'." },
      { title: "Cost is per second", body: "The price appears once the clip is loaded. Trim long clips first." },
      { title: "Generate", body: "Compare with the original in the Library." },
    ],
    ask: "Restyle ./street.mp4 as a hand painted anime scene, keep the camera move. Quote with the real length first.",
    mcp: [
      { title: "Upload the clip", body: "", tool: "upload_media" },
      { title: "Quote with the length", body: "", tool: "estimate_cost (input_video_seconds)" },
      { title: "Generate and wait", body: "", tool: "generate → get_generation" },
      { title: "Download", body: "", tool: "download_outputs" },
    ],
    prompts: [
      { label: "Anime", text: "Restyle the whole video as a hand painted anime illustration, keep the camera motion and timing" },
      { label: "Day to night", text: "Turn the scene into a rainy night with neon reflections, keep people and camera unchanged" },
      { label: "Claymation", text: "Transform everything into a stop motion claymation look, visible fingerprints on the clay" },
    ],
    tips: ["Say explicitly what must not change.", "Short clips (5–8 s) give the most consistent results."],
  },
  {
    slug: "extend",
    title: "Extend a shot",
    tagline: "The shot ended too soon? Continue it from its last frame.",
    category: "Edit",
    output: "video",
    channels: ["ui", "mcp"],
    art: "/art/use-cases/extend.webp",
    model: "bytedance/seedance-2.5/video-extend",
    sample: { video_url: "https://example.com/a.mp4", prompt: "cost preview" },
    uiHref: studioHref("video", "edit", "extend", "bytedance/seedance-2.5/video-extend"),
    ui: [
      { title: "Open Edit Video › Extend", body: "Upload the clip to continue." },
      { title: "Say what happens next", body: "Continue the action and the camera: 'the car keeps driving and the camera rises'." },
      { title: "Check the cost", body: "Then Generate." },
    ],
    ask: "Extend the last generation 5 more seconds: the car keeps driving along the cliff and the camera rises to reveal the sea.",
    mcp: [
      { title: "Find the clip", body: "Takes the last completed video from your history.", tool: "list_generations" },
      { title: "Quote the extension", body: "", tool: "estimate_cost" },
      { title: "Generate and wait", body: "", tool: "generate → get_generation" },
    ],
    prompts: [
      { label: "Reveal", text: "Continue the shot, the car keeps driving along the cliff road and the camera rises to reveal the sea at sunset" },
      { label: "Follow", text: "Continue seamlessly, the character keeps walking and turns the corner, handheld camera follows" },
      { label: "Ending", text: "Continue the shot and slowly pull back into a wide shot, fade the action to a calm ending" },
    ],
    tips: ["Extend a few times in a row to build longer shots.", "Keep the same style words as the original prompt."],
  },
  {
    slug: "reel-covers",
    title: "Reel covers in batch",
    tagline: "A set of vertical covers for social media, with room for the headline.",
    category: "Social",
    output: "image",
    channels: ["ui", "mcp"],
    art: "/art/use-cases/reel-covers.webp",
    model: "z-image/turbo",
    sample: { prompt: "cost preview", aspect_ratio: "9:16", resolution: "2k" },
    uiHref: studioHref("image", "create", "text", "z-image/turbo"),
    preset: "reel-cover",
    ui: [
      { title: "Open the Reel cover preset", body: "Or Image › Text to image with a fast model and 9:16." },
      { title: "Subject and mood", body: "One cover per subject; keep the same mood for the whole series." },
      { title: "Generate", body: "Images cost cents: generate several and pick." },
    ],
    ask: "Make 6 reel covers for my coffee shop, moody cinematic, room for a headline. Quote the batch.",
    mcp: [
      { title: "Plan the series", body: "The agent writes six subjects that fit your brand." },
      { title: "Quote the batch", body: "", tool: "generate_batch (dry_run)" },
      { title: "Generate, wait, download", body: "All six in one go into ./covers.", tool: "generate_batch → wait_generations → download_outputs" },
    ],
    prompts: [
      { label: "Latte art", text: "Vertical social media cover photo of a barista pouring latte art, moody cinematic, strong focal point, generous empty space in the upper third for a headline, no text" },
      { label: "Chef", text: "Vertical cover photo of a chef plating a dish under a single warm lamp, dark background, space at the top for a title, no text" },
      { label: "Runner", text: "Vertical cover photo of a runner at dawn on an empty bridge, retro film look, sky filling the upper third, no text" },
    ],
    tips: ["'no text' avoids fake letters in the image.", "Same mood words = consistent grid on your profile."],
  },
  {
    slug: "storyboard",
    title: "Storyboard from a script",
    tagline: "Your agent breaks a script into shots and generates a frame for each one.",
    category: "Agents",
    output: "image",
    channels: ["mcp"],
    art: "/art/use-cases/storyboard.webp",
    model: "higgsfield-ai/soul/v2/standard",
    sample: { prompt: "cost preview", aspect_ratio: "16:9", resolution: "1080p" },
    ask: "Read ./script.md, split it into 6 shots and generate a 16:9 frame for each with the same visual style. Quote the batch first and save them to ./storyboard.",
    mcp: [
      { title: "Read the script", body: "The agent reads the file and writes one shot description per beat (shot size, action, light)." },
      { title: "Pick a model", body: "Asks for the best text-to-image model for consistent film stills.", tool: "recommend_models" },
      { title: "Quote all frames", body: "One batch item per shot, same style suffix.", tool: "generate_batch (dry_run)" },
      { title: "Generate and collect", body: "Waits for all and saves shot-01.png … shot-06.png.", tool: "wait_generations → download_outputs" },
      { title: "Animate the keepers", body: "Optional: turns chosen frames into 5 s clips with image-to-video, quoted again." },
    ],
    prompts: [
      { label: "Style suffix", text: "cinematic film still, anamorphic, muted teal and orange palette, 35mm grain" },
      { label: "Shot line", text: "Wide shot: an astronaut crosses a red desert plain at dusk, tiny against the landscape" },
      { label: "Close-up", text: "Extreme close-up: a glowing blue flower reflected in the astronaut's visor" },
    ],
    tips: ["Give the agent one shared style suffix for all frames.", "Ask for shot sizes (wide, medium, close-up) to get a real storyboard rhythm."],
  },
  {
    slug: "agent-assets",
    title: "Assets for your codebase",
    tagline: "While coding, your agent generates the images a page needs and drops them into the repo.",
    category: "Agents",
    output: "image",
    channels: ["mcp"],
    art: "/art/use-cases/agent-assets.webp",
    model: "higgsfield-ai/soul/v2/standard",
    sample: { prompt: "cost preview", aspect_ratio: "16:9", resolution: "1080p" },
    ask: "This landing page needs a hero image and three feature illustrations. Generate them in our style, quote first, save to public/art as WebP and wire them into the page.",
    mcp: [
      { title: "Read the page", body: "The agent looks at the components to see which images are missing and their aspect ratios." },
      { title: "Quote the set", body: "", tool: "generate_batch (dry_run)" },
      { title: "Generate on your OK", body: "", tool: "generate_batch → wait_generations" },
      { title: "Save into the repo", body: "Downloads to public/art, converts to WebP and edits the JSX to use them.", tool: "download_outputs" },
      { title: "Reuse the recipe", body: "Saves the style as a preset for the next page.", tool: "save_preset" },
    ],
    prompts: [
      { label: "Hero", text: "Wide hero image for a coffee shop website, warm morning light over the counter, shallow depth of field, space on the left for a headline" },
      { label: "Feature", text: "Minimal still life of coffee beans and a ceramic cup on linen, top light, soft shadows, square crop" },
      { label: "Team", text: "Candid photo of two baristas laughing behind the counter, natural light, editorial style" },
    ],
    tips: ["Tell the agent the exact sizes the layout expects.", "Outputs are copied locally, so links never expire."],
  },
];

export const CATEGORIES = ["All", ...new Set(USE_CASES.map((u) => u.category))];
