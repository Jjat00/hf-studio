import type { ModelSummary } from "./types";

export type Mode = {
  key: string;
  label: string;
  icon: "type" | "image" | "layers" | "wand" | "clock" | "swap" | "move" | "sparkles" | "brush";
  defaultModel: string;
  filter: (m: ModelSummary) => boolean;
  hero: { title: string; subtitle: string; tone: "lime" | "pink" | "blue" | "amber" | "violet"; art: string };
  /** Etiquetas de las ranuras de medios propias de este modo: campo → [título, pista]. */
  labels?: Record<string, [string, string]>;
};

export type Tab = { key: string; label: string; modes: Mode[]; empty: EmptyState };

export type EmptyState = {
  title: string;
  steps: { title: string; body: string }[];
};

const has = (m: ModelSummary, cap: string) => m.capabilities.includes(cap);
const isVideo = (m: ModelSummary) => m.output === "video";

export const VIDEO_TABS: Tab[] = [
  {
    key: "create",
    label: "Create Video",
    empty: {
      title: "From concept to final cut in seconds",
      steps: [
        { title: "Input anything", body: "Upload a start and end frame, reference clips, or simply start with a text prompt." },
        { title: "Write the prompt", body: "Use natural language to direct the scene, the camera and the pacing." },
        { title: "Generate", body: "Receive high-fidelity video in minutes. Download, reuse or iterate on the result." },
      ],
    },
    modes: [
      {
        key: "text",
        label: "Text",
        icon: "type",
        defaultModel: "bytedance/seedance-2.0/text-to-video",
        filter: (m) => isVideo(m) && m.id.includes("text-to-video"),
        hero: { title: "Text to video", subtitle: "From prompt to cinematic shot", tone: "lime", art: "/art/text-to-video.webp" },
      },
      {
        key: "frames",
        label: "Start & End",
        icon: "image",
        defaultModel: "bytedance/seedance-2.0/image-to-video",
        filter: (m) => isVideo(m) && (m.id.includes("image-to-video") || m.id.includes("first-last-frame")),
        hero: { title: "Start & end frame", subtitle: "Animate an image or bridge two frames", tone: "blue", art: "/art/frames.webp" },
        labels: {
          image_url: ["Start frame", "The image the video starts from"],
          end_image_url: ["End frame", "Where the shot should land"],
        },
      },
      {
        key: "references",
        label: "References",
        icon: "layers",
        defaultModel: "bytedance/seedance-2.0/reference-to-video",
        filter: (m) =>
          isVideo(m) &&
          (has(m, "reference-to-video") || /(video|image)-reference/.test(m.id) || m.id.includes("cinema-studio")),
        hero: { title: "Video references", subtitle: "Copy camera, style and characters from your clips", tone: "violet", art: "/art/references.webp" },
        labels: {
          video_urls: ["Add reference videos", "Camera, motion or style to follow · up to 15s each"],
          image_urls: ["Add elements", "Characters, products or locations"],
        },
      },
    ],
  },
  {
    key: "genjutsu",
    label: "Genjutsu",
    empty: {
      title: "Turn one video into many",
      steps: [
        { title: "Add a reference video", body: "4 to 30 seconds. Its motion, timing and camera are kept." },
        { title: "Add your elements", body: "Up to eight characters, locations or products to recast the scene." },
        { title: "Generate", body: "Recast the motion, or swap specific elements while keeping the rest untouched." },
      ],
    },
    modes: [
      {
        key: "motion",
        label: "Motion transfer",
        icon: "move",
        defaultModel: "higgsfiled/genjutsu/motion-transfer/v1.0",
        filter: (m) => m.id.includes("genjutsu/motion-transfer"),
        hero: { title: "Higgsfield Genjutsu", subtitle: "Reality manipulation · recast the motion", tone: "lime", art: "/art/references.webp" },
        labels: {
          video_url: ["Add a reference video", "to extract motion · 4–30 seconds"],
          image_urls: ["Add your elements", "Characters, locations or products · up to 8"],
        },
      },
      {
        key: "swap",
        label: "Objects swap",
        icon: "swap",
        defaultModel: "higgsfiled/genjutsu/object-swap/v1.0",
        filter: (m) => m.id.includes("genjutsu/object-swap"),
        hero: { title: "Higgsfield Genjutsu", subtitle: "Reality manipulation · swap one element, keep the rest", tone: "violet", art: "/art/object-swap.webp" },
        labels: {
          video_url: ["Add a reference video", "4–30 seconds · at least 640×640 px per frame"],
          image_urls: ["Add the new object", "Product, outfit or prop to swap in · up to 8"],
        },
      },
    ],
  },
  {
    key: "edit",
    label: "Edit Video",
    empty: {
      title: "Turn one video into many",
      steps: [
        { title: "Upload a clip", body: "Start from your own footage or from a previous generation." },
        { title: "Describe the change", body: "Restyle it, swap objects or extend the shot without reshooting." },
        { title: "Keep the rest", body: "Everything you don't ask to change stays untouched." },
      ],
    },
    modes: [
      {
        key: "edit",
        label: "Edit",
        icon: "wand",
        defaultModel: "bytedance/seedance-2.5/video-edit",
        filter: (m) => has(m, "video-edit"),
        hero: { title: "Video edit", subtitle: "Rewrite a clip with a prompt", tone: "pink", art: "/art/video-edit.webp" },
        labels: { video_url: ["Add a video to edit", "MP4 clip to transform"] },
      },
      {
        key: "extend",
        label: "Extend",
        icon: "clock",
        defaultModel: "bytedance/seedance-2.5/video-extend",
        filter: (m) => has(m, "video-extend"),
        hero: { title: "Video extend", subtitle: "Continue the shot where it ended", tone: "amber", art: "/art/video-extend.webp" },
        labels: { video_url: ["Add a video to extend", "The new footage continues from its last frame"] },
      },
    ],
  },
  {
    key: "motion",
    label: "Motion Control",
    empty: {
      title: "From concept to final cut in seconds",
      steps: [
        { title: "Input anything", body: "Upload a motion reference video and an image of your character." },
        { title: "Write the prompt", body: "Optionally describe the scene, the outfit or the setting." },
        { title: "Generate with Kling", body: "Your character performs the motion, shot by shot." },
      ],
    },
    modes: [
      {
        key: "motion",
        label: "Motion transfer",
        icon: "move",
        defaultModel: "kling-video/v3/motion-control/std",
        filter: (m) => m.id.includes("motion-control"),
        hero: { title: "Motion control", subtitle: "Control motion with video references", tone: "lime", art: "/art/motion.webp" },
        labels: {
          video_url: ["Add motion to copy", "Video duration: 3–30 seconds"],
          image_url: ["Add your character", "Image with visible face and body"],
          image_urls: ["Add your character", "Image with visible face and body"],
        },
      },
    ],
  },
];

export const IMAGE_TABS: Tab[] = [
  {
    key: "create",
    label: "Create Image",
    empty: {
      title: "Visuals that look shot, not generated",
      steps: [
        { title: "Pick a model", body: "Soul, Recraft, Ideogram, Qwen, Grok or Z-Image." },
        { title: "Write the prompt", body: "Framing, light, lens and style in a single sentence." },
        { title: "Generate", body: "Iterate fast, then bring your best frame to video in one click." },
      ],
    },
    modes: [
      {
        key: "text",
        label: "Text to image",
        icon: "sparkles",
        defaultModel: "higgsfield-ai/soul/v2/standard",
        filter: (m) => m.output === "image" && has(m, "text-to-image"),
        hero: { title: "Text to image", subtitle: "Editorial photography from a sentence", tone: "pink", art: "/art/text-to-image.webp" },
      },
      {
        key: "edit",
        label: "Edit image",
        icon: "brush",
        defaultModel: "alibaba/qwen-image-3/edit",
        filter: (m) => m.output === "image" && (has(m, "edit") || has(m, "image-edit") || has(m, "image-references")),
        hero: { title: "Image edit", subtitle: "Change parts of a photo with a prompt", tone: "blue", art: "/art/image-edit.webp" },
        labels: { image_urls: ["Add images to edit", "The photo plus optional references"] },
      },
    ],
  },
];
