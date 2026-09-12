import {
    FFmpeg
} from "https://cdn.jsdelivr.net/npm/@ffmpeg/ffmpeg@0.12.10/+esm";

import {
    fetchFile,
    toBlobURL
} from "https://cdn.jsdelivr.net/npm/@ffmpeg/util@0.12.1/+esm";


/* =====================================================
   DOM ELEMENTS
===================================================== */

const videoInput = document.getElementById("videoInput");
const dropZone = document.getElementById("dropZone");

const uploadSection = document.getElementById("uploadSection");
const editorSection = document.getElementById("editorSection");

const videoPreview = document.getElementById("videoPreview");

const fileName = document.getElementById("fileName");
const fileSize = document.getElementById("fileSize");

const videoDuration = document.getElementById("videoDuration");
const videoResolution = document.getElementById("videoResolution");

const currentTime = document.getElementById("currentTime");
const totalTime = document.getElementById("totalTime");

const startRange = document.getElementById("startRange");
const endRange = document.getElementById("endRange");

const startTime = document.getElementById("startTime");
const endTime = document.getElementById("endTime");

const selectedDuration = document.getElementById("selectedDuration");

const previewButton = document.getElementById("previewButton");
const resetButton = document.getElementById("resetButton");
const newVideoButton = document.getElementById("newVideoButton");

const exportButton = document.getElementById("exportButton");
const cancelExportButton = document.getElementById("cancelExportButton");

const exportStatus = document.getElementById("exportStatus");

const exportProgressContainer = document.getElementById("exportProgressContainer");
const exportProgress = document.getElementById("exportProgress");

const downloadSection = document.getElementById("downloadSection");
const outputFileSize = document.getElementById("outputFileSize");
const downloadButton = document.getElementById("downloadButton");

const timelineProgress = document.getElementById("timelineProgress");
const selectionRegion = document.getElementById("selectionRegion");

// New: inline warning / error banners (added to markup — see HTML notes).
const uploadWarning = document.getElementById("uploadWarning");
const editorWarning = document.getElementById("editorWarning");

// New: image + text overlay controls (applied across the whole clip).
const videoPreviewContainer = document.querySelector(".video-preview-container");

const imageOverlayToggle = document.getElementById("imageOverlayToggle");
const imageOverlayControls = document.getElementById("imageOverlayControls");
const imageOverlayInput = document.getElementById("imageOverlayInput");
const imageOverlayPosition = document.getElementById("imageOverlayPosition");
const imageOverlaySize = document.getElementById("imageOverlaySize");
const imageOverlayOpacity = document.getElementById("imageOverlayOpacity");
const imageOverlayPreviewEl = document.getElementById("imageOverlayPreviewEl");

const textOverlayToggle = document.getElementById("textOverlayToggle");
const textOverlayControls = document.getElementById("textOverlayControls");
const textOverlayInput = document.getElementById("textOverlayInput");
const textOverlayPosition = document.getElementById("textOverlayPosition");
const textOverlayColor = document.getElementById("textOverlayColor");
const textOverlaySize = document.getElementById("textOverlaySize");
const textOverlayPreviewEl = document.getElementById("textOverlayPreviewEl");


/* =====================================================
   CONFIGURATION
===================================================== */

const ALLOWED_EXTENSIONS = ["mp4", "m4v", "mov", "webm", "mkv"];

const ALLOWED_MIME_TYPES = [
    "video/mp4",
    "video/webm",
    "video/quicktime",
    "video/x-matroska",
    "video/x-m4v",
    // Some mobile browsers (notably iOS Safari) report an empty or generic
    // type for .mov files picked from the camera roll — that case is
    // handled separately by falling back to the extension check.
    ""
];

// Soft thresholds trigger a visible warning but still allow the user to
// continue. Hard threshold blocks outright — the browser tab will very
// likely crash or hang before that point on most devices.
const WARN_SIZE_DESKTOP = 500 * 1024 * 1024;   // 500 MB
const WARN_SIZE_MOBILE = 150 * 1024 * 1024;    // 150 MB
const HARD_MAX_SIZE = 2 * 1024 * 1024 * 1024;  // 2 GB

const WARN_DURATION_SECONDS = 20 * 60;   // 20 minutes
const HARD_MAX_DURATION_SECONDS = 3 * 60 * 60; // 3 hours (sanity cap)

const FFMPEG_LOAD_TIMEOUT_MS = 45_000;

// Overlay feature configuration.
// A self-hosted font would be ideal (see the same-origin worker fix
// earlier in this file for why), but drawtext's fontfile is just a
// network fetch done by the worker, not a Worker-construction call — so
// it isn't subject to the same cross-origin restriction and a CDN font is
// fine here. DejaVu Sans is permissively licensed (Bitstream Vera-derived)
// and jsDelivr serves npm package files with CORS enabled for everyone.
const OVERLAY_FONT_URL = "https://cdn.jsdelivr.net/npm/dejavu-fonts-ttf@2.37.3/ttf/DejaVuSans-Bold.ttf";
const OVERLAY_FONT_FS_NAME = "overlay-font.ttf";
const OVERLAY_TEXT_FS_NAME = "overlay-caption.txt";

// Fixed pixel widths keep the overlay filter graph simple (no scale2ref
// needed). The overlay image is scaled to this width, aspect preserved.
const IMAGE_OVERLAY_SIZE_PX = {
    small: 120,
    medium: 220,
    large: 340
};

// Position presets shared by both overlays. Each returns ffmpeg filter
// expressions for x/y given the variable names used by that filter
// (overlay: main_w/main_h/overlay_w/overlay_h — drawtext: w/h/text_w/text_h).
const OVERLAY_POSITIONS = {
    "top-left": {
        overlay: { x: "20", y: "20" },
        drawtext: { x: "20", y: "20" }
    },
    "top-right": {
        overlay: { x: "main_w-overlay_w-20", y: "20" },
        drawtext: { x: "w-text_w-20", y: "20" }
    },
    "bottom-left": {
        overlay: { x: "20", y: "main_h-overlay_h-20" },
        drawtext: { x: "20", y: "h-text_h-20" }
    },
    "bottom-right": {
        overlay: { x: "main_w-overlay_w-20", y: "main_h-overlay_h-20" },
        drawtext: { x: "w-text_w-20", y: "h-text_h-20" }
    },
    "center": {
        overlay: { x: "(main_w-overlay_w)/2", y: "(main_h-overlay_h)/2" },
        drawtext: { x: "(w-text_w)/2", y: "(h-text_h)/2" }
    }
};

// CSS-side equivalents for the live on-page preview (not sent to FFmpeg).
const OVERLAY_POSITION_CSS = {
    "top-left": { top: "16px", left: "16px", right: "auto", bottom: "auto", transform: "none" },
    "top-right": { top: "16px", right: "16px", left: "auto", bottom: "auto", transform: "none" },
    "bottom-left": { bottom: "16px", left: "16px", top: "auto", right: "auto", transform: "none" },
    "bottom-right": { bottom: "16px", right: "16px", top: "auto", left: "auto", transform: "none" },
    "center": { top: "50%", left: "50%", right: "auto", bottom: "auto", transform: "translate(-50%, -50%)" }
};


/* =====================================================
   APPLICATION STATE
===================================================== */

let videoFile = null;
let videoURL = null;

let duration = 0;

let ffmpeg = null;
let ffmpegLoaded = false;
let ffmpegLoading = false;

let isProcessing = false;
let cancelRequested = false;

let outputBlob = null;
let outputURL = null;

let previewStopHandler = null;

let currentInputName = null;
let currentOutputName = null;

// Overlay state — persists across trim resets, cleared on "Choose Another Video".
let imageOverlayFile = null;
let imageOverlayPreviewURL = null;
let fontBytesCache = null; // cached after first fetch, reused across exports
let currentOverlayImageName = null;


/* =====================================================
   DEVICE / ENVIRONMENT HELPERS
===================================================== */

function isMobileDevice() {
    const ua = navigator.userAgent || "";
    return /Android|iPhone|iPad|iPod|Mobile/i.test(ua);
}

function getWarnSizeThreshold() {
    return isMobileDevice() ? WARN_SIZE_MOBILE : WARN_SIZE_DESKTOP;
}


/* =====================================================
   WARNING / ERROR BANNER HELPERS
===================================================== */

function showBanner(el, message, level) {
    if (!el) {
        // Fall back gracefully if the markup hasn't been updated yet.
        if (level === "error") {
            console.error(message);
        } else {
            console.warn(message);
        }
        return;
    }

    el.textContent = message;
    el.classList.remove("hidden", "warning", "error");
    el.classList.add(level === "error" ? "error" : "warning");
}

function clearBanner(el) {
    if (!el) {
        return;
    }
    el.textContent = "";
    el.classList.add("hidden");
    el.classList.remove("warning", "error");
}


/* =====================================================
   FRIENDLY ERROR MESSAGES
===================================================== */

function getFriendlyErrorMessage(error) {

    const raw = String(error && (error.message || error)) || "";
    const lower = raw.toLowerCase();

    if (lower.includes("out of memory") || lower.includes("memory access out of bounds")) {
        return "The video is too large to process on this device. Try a shorter clip or a smaller file.";
    }

    if (lower.includes("invalid data found") || lower.includes("could not find codec parameters")) {
        return "This file couldn't be read as a valid video. It may be corrupted or use an unsupported codec.";
    }

    if (lower.includes("no space left")) {
        return "Not enough temporary storage available in the browser to process this video.";
    }

    if (lower.includes("terminated") || lower.includes("aborted")) {
        return "Processing was stopped.";
    }

    if (lower.includes("network") || lower.includes("failed to fetch")) {
        return "A network problem interrupted loading the video engine. Check your connection and try again.";
    }

    if (lower.includes("filter") || lower.includes("drawtext") || lower.includes("overlay")) {
        return "There was a problem applying the image or text overlay. Try a smaller image, " +
            "shorter text, or turn one overlay off and export again.";
    }

    if (lower.includes("timed out")) {
        return "The video processing engine took too long to load. This can happen on a slow connection, " +
            "or if this site's security policy blocks loading a background worker script — try reloading the page.";
    }

    return "Unable to export this video. Try a smaller file or a shorter clip.";
}


/* =====================================================
   FFMPEG INITIALIZATION
   (includes the same-origin worker fix)
===================================================== */

function withTimeout(promise, ms, timeoutMessage) {
    let timer = null;
    const timeout = new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error(timeoutMessage)), ms);
    });
    return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

async function loadFFmpeg() {

    if (ffmpegLoaded && ffmpeg) {
        return true;
    }

    if (ffmpegLoading) {
        // Avoid kicking off a second concurrent load if the user double-taps
        // "Export" before the first load finishes.
        while (ffmpegLoading) {
            await new Promise((resolve) => setTimeout(resolve, 150));
        }
        return ffmpegLoaded;
    }

    ffmpegLoading = true;

    try {

        exportStatus.textContent = "Loading video processing engine...";
        clearBanner(editorWarning);

        ffmpeg = new FFmpeg();

        ffmpeg.on("log", ({ message }) => {
            console.log("[FFmpeg]", message);
        });

        ffmpeg.on("progress", ({ progress }) => {

            if (!isProcessing) {
                return;
            }

            const percentage = Math.min(100, Math.max(0, Math.round(progress * 100)));

            exportProgress.style.width = `${percentage}%`;
            exportStatus.textContent = `Processing video... ${percentage}%`;
        });

        // Must be the ESM core build, not UMD: our worker always runs as an
        // ES module (see classes.js: `new Worker(..., { type: "module" })`),
        // so it loads the core via dynamic `import()` rather than
        // `importScripts()`. The UMD build has no `export default`, so
        // importing it resolves to an empty module and fails with
        // "failed to import ffmpeg-core.js". The ESM build does export
        // `createFFmpegCore` as default, which is what's required here.
        const coreBaseURL = "https://cdn.jsdelivr.net/npm/@ffmpeg/core@0.12.6/dist/esm";

        // Same-origin worker fix.
        // The library normally creates its worker relative to wherever the
        // FFmpeg class itself was loaded from (jsDelivr), and several
        // browsers refuse to construct a Worker across origins:
        //   SecurityError: Failed to construct 'Worker': Script at
        //   'https://cdn.jsdelivr.net/.../worker.js' cannot be accessed
        //   from origin 'http://your-app-origin'.
        // The fix is to serve a self-contained worker script (no relative
        // imports — see static/js/ffmpeg-worker.js) from this app's own
        // origin and pass it as `classWorkerURL`. It must be an absolute
        // URL: a same-origin *relative* path would still resolve against
        // jsDelivr's origin internally, not this page's origin.
        // Note: this file is a static asset, not a Jinja template, so the
        // path below is a plain string rather than `url_for(...)` — it must
        // match wherever ffmpeg-worker.js is actually served from
        // (static/js/ffmpeg-worker.js in this project).
        const classWorkerURL = new URL(
            "/static/js/ffmpeg-worker.js",
            window.location.origin
        ).href;

        const [coreURL, wasmURL] = await withTimeout(
            Promise.all([
                toBlobURL(`${coreBaseURL}/ffmpeg-core.js`, "text/javascript"),
                toBlobURL(`${coreBaseURL}/ffmpeg-core.wasm`, "application/wasm")
            ]),
            FFMPEG_LOAD_TIMEOUT_MS,
            "Timed out loading the video processing engine."
        );

        await withTimeout(
            ffmpeg.load({ coreURL, wasmURL, classWorkerURL }),
            FFMPEG_LOAD_TIMEOUT_MS,
            "Timed out initializing the video processing engine."
        );

        ffmpegLoaded = true;
        exportStatus.textContent = "Video processing engine ready.";
        return true;

    } catch (error) {

        console.error("FFmpeg loading error:", error);

        ffmpegLoaded = false;
        ffmpeg = null;

        exportStatus.textContent = getFriendlyErrorMessage(error);
        return false;

    } finally {
        ffmpegLoading = false;
    }
}


/* =====================================================
   FILE VALIDATION
===================================================== */

function getFileExtension(name) {
    const parts = (name || "").split(".");
    if (parts.length < 2) {
        return "";
    }
    return parts.pop().toLowerCase();
}

/**
 * Validates format, size. Returns { ok, message, level } — level is
 * "error" (block) or "warning" (allow, but tell the user).
 */
function validateFile(file) {

    const extension = getFileExtension(file.name);
    const mimeOk = ALLOWED_MIME_TYPES.includes((file.type || "").toLowerCase());
    const extOk = ALLOWED_EXTENSIONS.includes(extension);

    // A file must at least look like a video by MIME type OR by a known
    // extension (mobile browsers frequently omit/garble the MIME type for
    // MOV files picked from the camera roll).
    const looksLikeVideo = (file.type || "").startsWith("video/") || extOk;

    if (!looksLikeVideo || (!mimeOk && !extOk)) {
        return {
            ok: false,
            level: "error",
            message: "Unsupported file type. Please choose an MP4, MOV, WebM or MKV video."
        };
    }

    if (file.size <= 0) {
        return {
            ok: false,
            level: "error",
            message: "This file appears to be empty."
        };
    }

    if (file.size > HARD_MAX_SIZE) {
        return {
            ok: false,
            level: "error",
            message: `This file is too large (over ${formatFileSize(HARD_MAX_SIZE)}). ` +
                "Please trim it down before uploading, or use a desktop video editor."
        };
    }

    const warnThreshold = getWarnSizeThreshold();

    if (file.size > warnThreshold) {
        return {
            ok: true,
            level: "warning",
            message: isMobileDevice()
                ? "This is a large video for a mobile device. Processing may be slow, use a lot of " +
                  "battery/data, or fail if the browser runs low on memory."
                : "This is a large video. Processing may take a while and use a lot of memory."
        };
    }

    return { ok: true, level: null, message: "" };
}

function validateDuration(seconds) {

    if (!Number.isFinite(seconds) || seconds <= 0) {
        return {
            ok: false,
            level: "error",
            message: "Couldn't read this video's duration. The file may be corrupted or use an unsupported format."
        };
    }

    if (seconds > HARD_MAX_DURATION_SECONDS) {
        return {
            ok: false,
            level: "error",
            message: "This video is too long to edit in the browser. Please use a shorter clip."
        };
    }

    if (seconds > WARN_DURATION_SECONDS) {
        return {
            ok: true,
            level: "warning",
            message: "This is a long video — exporting may take a while, especially on mobile."
        };
    }

    return { ok: true, level: null, message: "" };
}


/* =====================================================
   LOAD VIDEO
===================================================== */

function loadVideo(file) {

    clearBanner(uploadWarning);

    if (!file) {
        return;
    }

    const validation = validateFile(file);

    if (!validation.ok) {
        showBanner(uploadWarning, validation.message, "error");
        return;
    }

    if (validation.level === "warning") {
        showBanner(uploadWarning, validation.message, "warning");
    }

    cleanupOutput();
    resetFFmpegFilesystemState();

    videoFile = file;

    fileName.textContent = file.name;
    fileSize.textContent = formatFileSize(file.size);

    if (videoURL) {
        URL.revokeObjectURL(videoURL);
    }

    videoURL = URL.createObjectURL(file);
    videoPreview.src = videoURL;

    uploadSection.classList.add("hidden");
    editorSection.classList.remove("hidden");

    resetExportUI();
    clearBanner(editorWarning);

    videoPreview.currentTime = 0;

    // Load FFmpeg in the background so it's ready by the time the user hits
    // Export. Failures here don't block editing/preview — they're retried
    // when Export is actually clicked.
    loadFFmpeg();
}


/* =====================================================
   FILE INPUT
===================================================== */

videoInput.addEventListener("change", function () {
    if (this.files && this.files.length > 0) {
        loadVideo(this.files[0]);
    }
});


/* =====================================================
   DRAG & DROP
===================================================== */

dropZone.addEventListener("dragover", function (event) {
    event.preventDefault();
    dropZone.classList.add("drag-over");
});

dropZone.addEventListener("dragleave", function () {
    dropZone.classList.remove("drag-over");
});

dropZone.addEventListener("drop", function (event) {
    event.preventDefault();
    dropZone.classList.remove("drag-over");

    const files = event.dataTransfer.files;
    if (files && files.length > 0) {
        loadVideo(files[0]);
    }
});


/* =====================================================
   VIDEO METADATA
   (includes the classic WebM "Infinity duration" fix)
===================================================== */

videoPreview.addEventListener("loadedmetadata", function () {

    if (!Number.isFinite(videoPreview.duration)) {
        // Some WebM files report Infinity/NaN duration until the browser
        // has been forced to seek near the end at least once.
        const fixDuration = () => {
            videoPreview.removeEventListener("timeupdate", fixDuration);
            videoPreview.currentTime = 0;
            finalizeMetadata(videoPreview.duration);
        };
        videoPreview.addEventListener("timeupdate", fixDuration);
        videoPreview.currentTime = 1e101;
        return;
    }

    finalizeMetadata(videoPreview.duration);
});

function finalizeMetadata(rawDuration) {

    duration = rawDuration;

    const durationCheck = validateDuration(duration);

    if (!durationCheck.ok) {
        showBanner(editorWarning, durationCheck.message, "error");
        disableEditorControls(true);
        exportButton.disabled = true;
        return;
    }

    if (durationCheck.level === "warning") {
        showBanner(editorWarning, durationCheck.message, "warning");
    }

    videoDuration.textContent = formatTime(duration);
    totalTime.textContent = formatTime(duration);

    videoResolution.textContent = `${videoPreview.videoWidth} × ${videoPreview.videoHeight}`;

    startRange.min = 0;
    startRange.max = duration;
    startRange.value = 0;

    endRange.min = 0;
    endRange.max = duration;
    endRange.value = duration;

    updateSelection();
    updateTimeline();
}


/* =====================================================
   VIDEO TIME UPDATE
===================================================== */

videoPreview.addEventListener("timeupdate", function () {
    currentTime.textContent = formatTime(videoPreview.currentTime);
    updateTimeline();
});


/* =====================================================
   START RANGE
===================================================== */

startRange.addEventListener("input", function () {

    let start = Number(startRange.value);
    const end = Number(endRange.value);

    if (start >= end) {
        start = Math.max(0, end - 0.1);
        startRange.value = start;
    }

    videoPreview.currentTime = start;
    updateSelection();
});


/* =====================================================
   END RANGE
===================================================== */

endRange.addEventListener("input", function () {

    const start = Number(startRange.value);
    let end = Number(endRange.value);

    if (end <= start) {
        end = Math.min(duration, start + 0.1);
        endRange.value = end;
    }

    videoPreview.currentTime = end;
    updateSelection();
});


/* =====================================================
   UPDATE SELECTION
===================================================== */

function updateSelection() {

    const start = Number(startRange.value);
    const end = Number(endRange.value);

    startTime.textContent = formatTime(start);
    endTime.textContent = formatTime(end);
    selectedDuration.textContent = formatTime(end - start);

    updateSelectionRegion();
}


/* =====================================================
   SELECTION REGION
===================================================== */

function updateSelectionRegion() {

    if (!duration) {
        return;
    }

    const start = Number(startRange.value);
    const end = Number(endRange.value);

    const left = (start / duration) * 100;
    const right = (end / duration) * 100;

    selectionRegion.style.left = `${left}%`;
    selectionRegion.style.width = `${right - left}%`;
}


/* =====================================================
   PREVIEW SELECTION
===================================================== */

previewButton.addEventListener("click", function () {

    const start = Number(startRange.value);
    const end = Number(endRange.value);

    if (previewStopHandler) {
        videoPreview.removeEventListener("timeupdate", previewStopHandler);
    }

    videoPreview.currentTime = start;

    previewStopHandler = function () {
        if (videoPreview.currentTime >= end) {
            videoPreview.pause();
            videoPreview.currentTime = end;
            videoPreview.removeEventListener("timeupdate", previewStopHandler);
            previewStopHandler = null;
        }
    };

    videoPreview.addEventListener("timeupdate", previewStopHandler);
    videoPreview.play();
});


/* =====================================================
   RESET
===================================================== */

resetButton.addEventListener("click", function () {

    startRange.value = 0;
    endRange.value = duration;

    videoPreview.currentTime = 0;

    updateSelection();
    updateTimeline();

    resetExportUI();
    cleanupOutput();
});


/* =====================================================
   OVERLAY CONTROLS
   Wiring for the toggle sections, live on-page preview,
   and cleanup of the overlay image object URL.
===================================================== */

imageOverlayToggle.addEventListener("change", function () {
    imageOverlayControls.classList.toggle("hidden", !this.checked);
    updateImageOverlayPreview();
});

imageOverlayInput.addEventListener("change", function () {

    if (imageOverlayPreviewURL) {
        URL.revokeObjectURL(imageOverlayPreviewURL);
        imageOverlayPreviewURL = null;
    }

    const file = this.files && this.files[0];
    imageOverlayFile = file || null;

    if (file) {
        imageOverlayPreviewURL = URL.createObjectURL(file);
    }

    updateImageOverlayPreview();
});

imageOverlayPosition.addEventListener("change", updateImageOverlayPreview);
imageOverlaySize.addEventListener("change", updateImageOverlayPreview);
imageOverlayOpacity.addEventListener("input", updateImageOverlayPreview);

function updateImageOverlayPreview() {

    const enabled = imageOverlayToggle.checked && imageOverlayPreviewURL;

    if (!enabled) {
        imageOverlayPreviewEl.classList.add("hidden");
        imageOverlayPreviewEl.removeAttribute("src");
        return;
    }

    imageOverlayPreviewEl.src = imageOverlayPreviewURL;
    imageOverlayPreviewEl.style.opacity = imageOverlayOpacity.value;

    applyPreviewPosition(imageOverlayPreviewEl, imageOverlayPosition.value);

    imageOverlayPreviewEl.classList.remove("hidden");
}

textOverlayToggle.addEventListener("change", function () {
    textOverlayControls.classList.toggle("hidden", !this.checked);
    updateTextOverlayPreview();
});

textOverlayInput.addEventListener("input", updateTextOverlayPreview);
textOverlayPosition.addEventListener("change", updateTextOverlayPreview);
textOverlayColor.addEventListener("input", updateTextOverlayPreview);
textOverlaySize.addEventListener("input", updateTextOverlayPreview);

function updateTextOverlayPreview() {

    const text = textOverlayInput.value.trim();
    const enabled = textOverlayToggle.checked && text.length > 0;

    if (!enabled) {
        textOverlayPreviewEl.classList.add("hidden");
        return;
    }

    textOverlayPreviewEl.textContent = text;
    textOverlayPreviewEl.style.color = textOverlayColor.value;

    // Scale preview font size roughly to the on-screen preview width vs
    // the video's real resolution so it's a reasonable approximation, not
    // an exact match (the export uses the real resolution's pixel size).
    const previewScale = videoPreview.clientWidth && videoPreview.videoWidth
        ? videoPreview.clientWidth / videoPreview.videoWidth
        : 1;

    textOverlayPreviewEl.style.fontSize =
        `${Math.max(10, Number(textOverlaySize.value) * previewScale)}px`;

    applyPreviewPosition(textOverlayPreviewEl, textOverlayPosition.value);

    textOverlayPreviewEl.classList.remove("hidden");
}

function applyPreviewPosition(el, positionKey) {
    const pos = OVERLAY_POSITION_CSS[positionKey] || OVERLAY_POSITION_CSS["top-left"];
    el.style.top = pos.top;
    el.style.left = pos.left;
    el.style.right = pos.right;
    el.style.bottom = pos.bottom;
    el.style.transform = pos.transform;
}

function resetOverlayState() {

    imageOverlayToggle.checked = false;
    imageOverlayControls.classList.add("hidden");
    imageOverlayInput.value = "";
    imageOverlayPosition.value = "top-right";
    imageOverlaySize.value = "medium";
    imageOverlayOpacity.value = "1";

    if (imageOverlayPreviewURL) {
        URL.revokeObjectURL(imageOverlayPreviewURL);
    }
    imageOverlayPreviewURL = null;
    imageOverlayFile = null;

    textOverlayToggle.checked = false;
    textOverlayControls.classList.add("hidden");
    textOverlayInput.value = "";
    textOverlayPosition.value = "bottom-right";
    textOverlayColor.value = "#ffffff";
    textOverlaySize.value = "32";

    updateImageOverlayPreview();
    updateTextOverlayPreview();
}

// Re-run once metadata loads so the font-scaled text preview lines up with
// the actual video dimensions rather than assuming a 1:1 scale.
videoPreview.addEventListener("loadedmetadata", updateTextOverlayPreview);


/* =====================================================
   EXPORT VIDEO
===================================================== */

exportButton.addEventListener("click", async function () {

    if (!videoFile || isProcessing) {
        return;
    }

    const start = Number(startRange.value);
    const end = Number(endRange.value);

    if (end <= start) {
        showBanner(editorWarning, "Please select a valid range.", "error");
        return;
    }

    if (!ffmpegLoaded) {
        const loaded = await loadFFmpeg();
        if (!loaded) {
            return;
        }
    }

    await startExport(start, end);
});


/* =====================================================
   AUDIO STREAM DETECTION
   Videos without an audio track no longer fail export —
   we probe first and skip audio encoding when there isn't one.
===================================================== */

async function detectAudioStream(inputName) {

    let hasAudio = false;

    const logHandler = ({ message }) => {
        if (/Stream #\d+:\d+.*Audio:/i.test(message)) {
            hasAudio = true;
        }
    };

    ffmpeg.on("log", logHandler);

    try {
        // Running ffmpeg with -i and no output always "fails" (non-zero
        // exit) — that's expected and only used to read the stream list
        // from the log output.
        await ffmpeg.exec(["-i", inputName]);
    } catch (error) {
        // Ignored — see note above.
    } finally {
        if (typeof ffmpeg.off === "function") {
            ffmpeg.off("log", logHandler);
        }
    }

    return hasAudio;
}


/* =====================================================
   OVERLAY FILTER BUILDING
===================================================== */

async function ensureFontLoaded() {
    if (fontBytesCache) {
        return fontBytesCache;
    }
    fontBytesCache = await fetchFile(OVERLAY_FONT_URL);
    return fontBytesCache;
}

function getImageOverlaySettings() {
    if (!imageOverlayToggle.checked || !imageOverlayFile) {
        return null;
    }
    return {
        file: imageOverlayFile,
        position: imageOverlayPosition.value,
        widthPx: IMAGE_OVERLAY_SIZE_PX[imageOverlaySize.value] || IMAGE_OVERLAY_SIZE_PX.medium,
        opacity: Number(imageOverlayOpacity.value) || 1
    };
}

function getTextOverlaySettings() {
    const text = textOverlayInput.value.trim();
    if (!textOverlayToggle.checked || !text) {
        return null;
    }
    return {
        text,
        position: textOverlayPosition.value,
        color: textOverlayColor.value,
        fontSize: Number(textOverlaySize.value) || 32
    };
}

/**
 * Writes whatever overlay assets are needed into the FFmpeg virtual
 * filesystem and returns everything startExport needs to assemble the
 * command: extra -i inputs, the filter_complex string, the label to map
 * as output video, and the list of written filenames (for cleanup).
 */
async function prepareOverlayAssets(imageSettings, textSettings) {

    const extraInputs = [];
    const filterParts = [];
    const writtenFiles = [];

    let lastLabel = "0:v";
    let nextInputIndex = 1;

    if (imageSettings) {

        const ext = getFileExtension(imageSettings.file.name) || "png";
        const overlayImageName = `overlay-image.${ext}`;

        await ffmpeg.writeFile(overlayImageName, await fetchFile(imageSettings.file));
        writtenFiles.push(overlayImageName);
        currentOverlayImageName = overlayImageName;

        // `-loop 1` is essential here: without it, ffmpeg treats the
        // image as a single-frame input, so the watermark would only
        // appear in the first output frame instead of across the whole
        // clip. Looping makes it behave like a continuous video source.
        extraInputs.push("-loop", "1", "-i", overlayImageName);

        const pos = OVERLAY_POSITIONS[imageSettings.position] || OVERLAY_POSITIONS["top-right"];
        const scaledLabel = "wm";
        const composedLabel = "ovimg";

        filterParts.push(
            `[${nextInputIndex}:v]scale=${imageSettings.widthPx}:-1,format=rgba,` +
            `colorchannelmixer=aa=${imageSettings.opacity}[${scaledLabel}]`
        );
        filterParts.push(
            `[${lastLabel}][${scaledLabel}]overlay=${pos.overlay.x}:${pos.overlay.y}[${composedLabel}]`
        );

        lastLabel = composedLabel;
        nextInputIndex++;
    }

    if (textSettings) {

        const fontBytes = await ensureFontLoaded();
        await ffmpeg.writeFile(OVERLAY_FONT_FS_NAME, fontBytes);
        writtenFiles.push(OVERLAY_FONT_FS_NAME);

        // Written as a file (textfile=...) rather than inlined into the
        // filter string — this sidesteps FFmpeg filtergraph escaping
        // rules entirely (colons, quotes, backslashes, % signs in the
        // user's caption would otherwise need careful escaping).
        await ffmpeg.writeFile(OVERLAY_TEXT_FS_NAME, textSettings.text);
        writtenFiles.push(OVERLAY_TEXT_FS_NAME);

        const pos = OVERLAY_POSITIONS[textSettings.position] || OVERLAY_POSITIONS["bottom-right"];
        const composedLabel = "ovtext";

        filterParts.push(
            `[${lastLabel}]drawtext=fontfile=${OVERLAY_FONT_FS_NAME}:` +
            `textfile=${OVERLAY_TEXT_FS_NAME}:` +
            `fontsize=${textSettings.fontSize}:fontcolor=${textSettings.color}:` +
            `x=${pos.drawtext.x}:y=${pos.drawtext.y}:` +
            `box=1:boxcolor=black@0.4:boxborderw=6[${composedLabel}]`
        );

        lastLabel = composedLabel;
    }

    return {
        extraInputs,
        filterComplex: filterParts.join(";"),
        outputLabel: lastLabel,
        writtenFiles
    };
}


/* =====================================================
   START EXPORT
===================================================== */

async function startExport(start, end) {

    isProcessing = true;
    cancelRequested = false;

    cleanupOutput();
    clearBanner(editorWarning);

    disableEditorControls(true);

    exportProgress.style.width = "0%";
    exportProgressContainer.classList.remove("hidden");
    cancelExportButton.classList.remove("hidden");
    downloadSection.classList.add("hidden");

    const inputName = `input.${getFileExtension(videoFile.name) || "mp4"}`;
    const outputName = "trimmed-video.mp4";

    currentInputName = inputName;
    currentOutputName = outputName;

    const imageSettings = getImageOverlaySettings();
    const textSettings = getTextOverlaySettings();
    const hasOverlays = Boolean(imageSettings || textSettings);

    let overlayFiles = [];

    try {

        if (cancelRequested) {
            throw new Error("terminated");
        }

        exportStatus.textContent = "Reading video...";

        await ffmpeg.writeFile(inputName, await fetchFile(videoFile));

        if (cancelRequested) {
            throw new Error("terminated");
        }

        exportStatus.textContent = "Checking audio track...";

        const hasAudio = await detectAudioStream(inputName);

        if (cancelRequested) {
            throw new Error("terminated");
        }

        const clipDuration = end - start;

        const audioArgs = hasAudio
            ? ["-c:a", "aac", "-b:a", "128k"]
            : ["-an"];

        let execArgs;

        if (hasOverlays) {

            exportStatus.textContent = "Preparing overlays...";

            const overlay = await prepareOverlayAssets(imageSettings, textSettings);
            overlayFiles = overlay.writtenFiles;

            if (cancelRequested) {
                throw new Error("terminated");
            }

            exportStatus.textContent = "Processing video...";

            execArgs = [
                "-ss", String(start),
                "-i", inputName,
                ...overlay.extraInputs,
                "-t", String(clipDuration),
                "-filter_complex", overlay.filterComplex,
                "-map", `[${overlay.outputLabel}]`,
                ...(hasAudio ? ["-map", "0:a"] : []),
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-crf", "23",
                ...audioArgs,
                "-movflags", "+faststart",
                outputName
            ];

        } else {

            exportStatus.textContent = "Processing video...";

            execArgs = [
                "-ss", String(start),
                "-i", inputName,
                "-t", String(clipDuration),
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-crf", "23",
                ...audioArgs,
                "-movflags", "+faststart",
                outputName
            ];
        }

        await ffmpeg.exec(execArgs);

        if (cancelRequested) {
            throw new Error("terminated");
        }

        const data = await ffmpeg.readFile(outputName);

        outputBlob = new Blob([data.buffer], { type: "video/mp4" });
        outputURL = URL.createObjectURL(outputBlob);

        outputFileSize.textContent = formatFileSize(outputBlob.size);

        exportProgress.style.width = "100%";
        exportStatus.textContent = "Video is ready.";

        downloadSection.classList.remove("hidden");

    } catch (error) {

        console.error("Export error:", error);

        if (cancelRequested) {
            exportStatus.textContent = "Processing cancelled.";
        } else {
            showBanner(editorWarning, getFriendlyErrorMessage(error), "error");
            exportStatus.textContent = "Export failed.";
        }

    } finally {

        // Always attempt to clean the virtual filesystem, whether the
        // export succeeded, failed, or was cancelled — this is what stops
        // memory/disk usage inside the FFmpeg instance from building up
        // across repeated exports.
        await safeDeleteFile(inputName);
        await safeDeleteFile(outputName);

        for (const name of overlayFiles) {
            await safeDeleteFile(name);
        }

        currentInputName = null;
        currentOutputName = null;
        currentOverlayImageName = null;

        isProcessing = false;
        cancelRequested = false;

        disableEditorControls(false);
        cancelExportButton.classList.add("hidden");
    }
}


/* =====================================================
   CANCEL EXPORT
===================================================== */

cancelExportButton.addEventListener("click", function () {

    if (!isProcessing) {
        return;
    }

    cancelRequested = true;

    exportStatus.textContent = "Cancelling processing...";

    // Terminating the worker is the only reliable way to stop FFmpeg mid
    // -exec (it doesn't support cooperative cancellation). The instance is
    // discarded and rebuilt on the next export/load so state stays clean.
    if (ffmpeg) {
        try {
            ffmpeg.terminate();
        } catch (error) {
            console.warn("Error terminating FFmpeg:", error);
        }
    }

    ffmpeg = null;
    ffmpegLoaded = false;
    ffmpegLoading = false;

    exportProgressContainer.classList.add("hidden");
    cancelExportButton.classList.add("hidden");
});


/* =====================================================
   DOWNLOAD VIDEO
   Output stays available until the user downloads it or
   starts a new export / loads a new video / resets.
===================================================== */

downloadButton.addEventListener("click", function () {

    if (!outputURL) {
        return;
    }

    const link = document.createElement("a");
    link.href = outputURL;
    link.download = createOutputFileName(videoFile.name);

    document.body.appendChild(link);
    link.click();
    link.remove();
});


/* =====================================================
   DISABLE CONTROLS
===================================================== */

function disableEditorControls(disabled) {
    exportButton.disabled = disabled;
    previewButton.disabled = disabled;
    resetButton.disabled = disabled;
    newVideoButton.disabled = disabled;
    startRange.disabled = disabled;
    endRange.disabled = disabled;
}


/* =====================================================
   CHOOSE ANOTHER VIDEO
===================================================== */

newVideoButton.addEventListener("click", function () {

    if (isProcessing) {
        return;
    }

    cleanupOutput();
    resetFFmpegFilesystemState();
    resetOverlayState();

    videoPreview.pause();

    if (videoURL) {
        URL.revokeObjectURL(videoURL);
    }

    videoURL = null;
    videoFile = null;
    duration = 0;

    videoPreview.removeAttribute("src");
    videoPreview.load();

    videoInput.value = "";

    editorSection.classList.add("hidden");
    uploadSection.classList.remove("hidden");

    resetExportUI();
    clearBanner(uploadWarning);
    clearBanner(editorWarning);

    // Release the wasm engine's memory entirely between sessions rather
    // than keeping it resident for the lifetime of the page. It's reloaded
    // lazily the next time a video is picked.
    if (ffmpeg && !isProcessing) {
        try {
            ffmpeg.terminate();
        } catch (error) {
            console.warn("Error terminating FFmpeg:", error);
        }
    }

    ffmpeg = null;
    ffmpegLoaded = false;
    ffmpegLoading = false;
});


/* =====================================================
   CLEAN OUTPUT
===================================================== */

function cleanupOutput() {

    if (outputURL) {
        URL.revokeObjectURL(outputURL);
    }

    outputURL = null;
    outputBlob = null;

    downloadSection.classList.add("hidden");
}


/* =====================================================
   RESET FFMPEG VIRTUAL FILESYSTEM STATE
   Best-effort cleanup of any leftover files from an
   interrupted previous run (e.g. a cancelled export).
===================================================== */

function resetFFmpegFilesystemState() {

    if (!ffmpeg || !ffmpegLoaded) {
        currentInputName = null;
        currentOutputName = null;
        currentOverlayImageName = null;
        return;
    }

    if (currentInputName) {
        safeDeleteFile(currentInputName);
    }
    if (currentOutputName) {
        safeDeleteFile(currentOutputName);
    }
    if (currentOverlayImageName) {
        safeDeleteFile(currentOverlayImageName);
    }
    safeDeleteFile(OVERLAY_FONT_FS_NAME);
    safeDeleteFile(OVERLAY_TEXT_FS_NAME);

    currentInputName = null;
    currentOutputName = null;
    currentOverlayImageName = null;
}


/* =====================================================
   RESET EXPORT UI
===================================================== */

function resetExportUI() {
    exportStatus.textContent = "";
    exportProgress.style.width = "0%";
    exportProgressContainer.classList.add("hidden");
    cancelExportButton.classList.add("hidden");
    downloadSection.classList.add("hidden");
}


/* =====================================================
   SAFE FFMPEG FILE DELETE
===================================================== */

async function safeDeleteFile(name) {
    if (!ffmpeg) {
        return;
    }
    try {
        await ffmpeg.deleteFile(name);
    } catch (error) {
        // Expected if the file was never created (e.g. failure before
        // writeFile completed) — not worth surfacing to the user.
        console.warn(`Could not delete ${name}`);
    }
}


/* =====================================================
   UPDATE TIMELINE
===================================================== */

function updateTimeline() {
    if (!duration) {
        return;
    }
    const percentage = (videoPreview.currentTime / duration) * 100;
    timelineProgress.style.width = `${percentage}%`;
}


/* =====================================================
   CREATE OUTPUT FILE NAME
===================================================== */

function createOutputFileName(originalName) {
    const index = originalName.lastIndexOf(".");
    const name = index === -1 ? originalName : originalName.substring(0, index);
    return `${name}-trimmed.mp4`;
}


/* =====================================================
   FORMAT FILE SIZE
===================================================== */

function formatFileSize(bytes) {
    if (!Number.isFinite(bytes)) {
        return "-";
    }
    if (bytes < 1024) {
        return `${bytes} B`;
    }
    const units = ["KB", "MB", "GB"];
    let size = bytes / 1024;
    let unitIndex = 0;
    while (size >= 1024 && unitIndex < units.length - 1) {
        size /= 1024;
        unitIndex++;
    }
    return `${size.toFixed(2)} ${units[unitIndex]}`;
}


/* =====================================================
   FORMAT TIME
===================================================== */

function formatTime(seconds) {
    if (!Number.isFinite(seconds)) {
        return "00:00";
    }
    seconds = Math.max(0, seconds);
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    if (hours > 0) {
        return `${String(hours).padStart(2, "0")}:` +
            `${String(minutes).padStart(2, "0")}:` +
            `${String(remainingSeconds).padStart(2, "0")}`;
    }
    return `${String(minutes).padStart(2, "0")}:` +
        `${String(remainingSeconds).padStart(2, "0")}`;
}


/* =====================================================
   PAGE CLEANUP
===================================================== */

window.addEventListener("beforeunload", function () {
    cleanupOutput();
    if (videoURL) {
        URL.revokeObjectURL(videoURL);
    }
    if (imageOverlayPreviewURL) {
        URL.revokeObjectURL(imageOverlayPreviewURL);
    }
    if (ffmpeg) {
        try {
            ffmpeg.terminate();
        } catch (error) {
            // Ignored — page is unloading anyway.
        }
    }
});