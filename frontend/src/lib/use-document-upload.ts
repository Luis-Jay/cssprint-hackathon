"use client";

import { useState } from "react";
import { toast } from "sonner";
import { uploadDocument } from "@/lib/api";
import { useCompliance } from "@/lib/compliance-store";
import { downscaleImage } from "@/lib/image";
import type { Stage } from "@/lib/roadmap-data";

/**
 * Upload one document for a stage and run the inspection agent over it.
 *
 * Shared by the stage card's upload box and GabAI's Re-upload button,
 * so both verify the same way and report findings into the chat.
 */
export function useDocumentUpload(stage: Stage | undefined) {
  const { sessionId, completeStage, recordUpload, pushAgentMessage, markSubStepsChecked } =
    useCompliance();
  const [busy, setBusy] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);

  const upload = async (file?: File) => {
    if (!stage || busy) return;
    const label = file?.name || stage.uploadLabel;
    setFileName(file?.name ?? null);
    setBusy(true);

    if (!sessionId || !file) {
      // No backend session (or a drop with no file): keep the old optimistic
      // behaviour rather than blocking the user.
      setTimeout(() => {
        setBusy(false);
        completeStage(stage.id);
        toast.success(`Recorded: ${label}`, {
          description: `Stage ${stage.index} marked complete.`,
        });
      }, 600);
      return;
    }

    try {
      // Shrink camera photos before sending
      const toSend = await downscaleImage(file);
      const res = await uploadDocument(sessionId, file.name, toSend, stage.index);
      const vr = res.verification_results;

      // Surface the findings in the chat straight away
      pushAgentMessage({
        id: crypto.randomUUID(),
        agent: res.agent ?? "Inspection Readiness Agent",
        text: res.message,
        stageId: stage.id,
        verification: vr?.documents,
        trace: res.trace?.events,
        traceMs: res.trace?.duration_ms,
      });

      // Tick every requirement the document satisfied, even when the stage as a whole is not done
      const satisfied = (vr?.documents ?? [])
        .filter((d) => d.status === "complete")
        .map((d) => d.document_name.trim().toLowerCase());
      if (satisfied.length) {
        markSubStepsChecked(
          stage.subSteps
            .filter((ss) => satisfied.includes(ss.label.trim().toLowerCase()))
            .map((ss) => ss.id),
        );
      }

      // Only advance when the document actually satisfies the stage
      if (vr?.passed) {
        recordUpload(stage.id, file.name);
        rememberFile(stage.id, file);
        completeStage(stage.id);
        toast.success(`Looks right: ${label}`, {
          description: `Stage ${stage.index} is done. The issuing office has the final say.`,
        });
      } else if (vr?.unreadable) {
        toast.warning(`Could not read ${label}`, {
          description: vr.documents?.[0]?.notes ?? "See GabAI for details.",
        });
      } else {
        toast.error(`${label} does not satisfy this stage`, {
          description: vr?.documents?.[0]?.notes ?? res.message,
        });
      }
    } catch (err) {
      toast.error(`Could not verify ${label}`, {
        description:
          err instanceof Error ? err.message : "The compliance service is unreachable.",
      });
    } finally {
      setBusy(false);
    }
  };

  return { upload, busy, fileName };
}

/**
 * Links to the uploaded files, for this browser session only. The backend
 * keeps the extracted text, not the file, so the link is gone after a reload.
 */
const fileUrls = new Map<string, string>();

function rememberFile(stageId: string, file: File) {
  const previous = fileUrls.get(stageId);
  if (previous) URL.revokeObjectURL(previous);
  fileUrls.set(stageId, URL.createObjectURL(file));
}

export function uploadedFileUrl(stageId: string): string | undefined {
  return fileUrls.get(stageId);
}

/** File types the inspection agent checks. Text files are refused: anyone can type a certificate. */
export const UPLOAD_ACCEPT =
  ".pdf,.jpg,.jpeg,.png,.webp,.heic,.heif,application/pdf,image/jpeg,image/png,image/webp,image/heic,image/heif";
