/** Downscale an image before uploading it */

/**
 * Claude scales anything longer than this down on its own, so sending more
 * pixels buys nothing and costs upload time.
 */
const MAX_EDGE = 1568;

/** Stay clear of the model's ~5MB attachment ceiling once base64-encoded. */
const MAX_BYTES = 2_800_000;

/** Quality steps to try, in order, until the result fits. */
const QUALITY_STEPS = [0.85, 0.7, 0.55, 0.4];

function isResizableImage(file: File): boolean {
  return /^image\/(jpeg|png|webp)$/.test(file.type);
}

async function toBlob(
  canvas: HTMLCanvasElement,
  quality: number,
): Promise<Blob | null> {
  return new Promise((resolve) =>
    canvas.toBlob((b) => resolve(b), "image/jpeg", quality),
  );
}

/** Return a version of `file` small enough to send, or the original when no work is needed */
export async function downscaleImage(file: File): Promise<File> {
  if (!isResizableImage(file)) return file;
  if (file.size <= MAX_BYTES) return file;

  try {
    const bitmap = await createImageBitmap(file);
    const longest = Math.max(bitmap.width, bitmap.height);
    const scale = Math.min(1, MAX_EDGE / longest);

    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);

    const ctx = canvas.getContext("2d");
    if (!ctx) return file;
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close?.();

    // Re-encode at descending quality until it fits
    for (const quality of QUALITY_STEPS) {
      const blob = await toBlob(canvas, quality);
      if (!blob) continue;
      if (blob.size <= MAX_BYTES) {
        const renamed = file.name.replace(/\.(png|webp|jpeg|jpg)$/i, "") + ".jpg";
        return new File([blob], renamed, {
          type: "image/jpeg",
          lastModified: file.lastModified,
        });
      }
    }

    return file;
  } catch {
    // Unsupported codec, memory pressure, OffscreenCanvas quirks - fall back
    // to the original rather than failing the upload.
    return file;
  }
}
