"use client";

import {
  type PropsWithChildren,
  useState,
  type FC,
  isValidElement,
} from "react";
import {
  AttachmentPrimitive,
  ComposerPrimitive,
  MessagePrimitive,
  useAuiState,
  useAui,
} from "@assistant-ui/react";
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogTrigger,
} from "./ui/dialog";
import {
  CloseActionIcon,
  PlusActionIcon,
} from "./action-icons";
import { TooltipIconButton } from "./tooltip-icon-button";
import { DotMatrix } from "../DotMatrix";
import { useAttachmentSrc } from "./hooks/use-attachment-src";
import { cn } from "./cn";

type AttachmentPreviewProps = {
  src: string;
};

const AttachmentPreview: FC<AttachmentPreviewProps> = ({ src }) => {
  const [isLoaded, setIsLoaded] = useState(false);
  return (
    <img
      src={src}
      alt="Attachment preview"
      className={cn(
        "block h-auto max-h-[80vh] w-auto max-w-full object-contain",
        isLoaded
          ? "aui-attachment-preview-image-loaded opacity-100"
          : "aui-attachment-preview-image-loading opacity-0",
      )}
      onLoad={() => setIsLoaded(true)}
    />
  );
};

const AttachmentPreviewDialog: FC<PropsWithChildren> = ({ children }) => {
  const src = useAttachmentSrc();

  if (!src) return children;

  return (
    <Dialog>
      <DialogTrigger
        className="aui-attachment-preview-trigger cursor-zoom-in"
        asChild
      >
        {isValidElement(children) ? (
          children
        ) : (
          <button type="button">{children}</button>
        )}
      </DialogTrigger>
      <DialogContent className="aui-attachment-preview-dialog-content rounded-none border shadow-none p-2 sm:max-w-3xl">
        <DialogTitle className="aui-sr-only sr-only">
          Image Attachment Preview
        </DialogTitle>
        <div className="aui-attachment-preview relative mx-auto flex max-h-[80dvh] w-full items-center justify-center overflow-hidden">
          <AttachmentPreview src={src} />
        </div>
      </DialogContent>
    </Dialog>
  );
};

const attachmentTypeLabel = (type: string) => {
  switch (type) {
    case "image":
      return "image";
    case "document":
      return "document";
    case "file":
      return "file";
    default:
      return type;
  }
};

const AttachmentChipBody: FC<{
  typeLabel: string;
  isUploading: boolean;
  isError: boolean;
}> = ({ typeLabel, isUploading, isError }) => (
  <span className="aui-attachment-chip-body inline-flex min-w-0 items-center gap-1.5">
    {isUploading ? (
      <DotMatrix state="loading" label="Uploading" className="size-3.5" />
    ) : null}
    {isError ? (
      <DotMatrix state="error" label="Upload failed" className="size-3.5" />
    ) : null}
    <span className="aui-attachment-chip-name min-w-0 truncate">
      <AttachmentPrimitive.Name />
    </span>
    <span className="aui-attachment-chip-type shrink-0">{typeLabel}</span>
  </span>
);

const AttachmentUI: FC = () => {
  const aui = useAui();
  const isComposer = aui.attachment.source !== "message";

  const isImage = useAuiState((s) => s.attachment.type === "image");
  const typeLabel = useAuiState((s) => attachmentTypeLabel(s.attachment.type));

  const uploadState = useAuiState((s) =>
    s.attachment.status.type === "running"
      ? "uploading"
      : s.attachment.status.type === "incomplete" &&
          s.attachment.status.reason === "error"
        ? "error"
        : undefined,
  );
  const isUploading = uploadState === "uploading";
  const isError = uploadState === "error";

  const errorMessage = useAuiState((s) =>
    s.attachment.status.type === "incomplete" &&
    s.attachment.status.reason === "error"
      ? (s.attachment.status.message ?? "Upload failed")
      : undefined,
  );

  const body = (
    <span
      className="aui-attachment-chip-hit min-w-0"
      role="button"
      tabIndex={0}
      title={errorMessage}
      aria-label={`${typeLabel} attachment${
        isError ? ", upload failed" : isUploading ? ", uploading" : ""
      }`}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          e.currentTarget.click();
        } else if (e.key === " ") {
          e.preventDefault();
        }
      }}
      onKeyUp={(e) => {
        if (e.key === " ") e.currentTarget.click();
      }}
    >
      <AttachmentChipBody
        typeLabel={typeLabel}
        isUploading={isUploading}
        isError={isError}
      />
    </span>
  );

  return (
    <AttachmentPrimitive.Root
      className={cn("aui-attachment-root relative", isError && "is-error")}
    >
      <div className="aui-attachment-chip">
        {isImage ? (
          <AttachmentPreviewDialog>{body}</AttachmentPreviewDialog>
        ) : (
          body
        )}
        {isComposer ? <AttachmentRemove /> : null}
      </div>
    </AttachmentPrimitive.Root>
  );
};

const AttachmentRemove: FC = () => {
  return (
    <AttachmentPrimitive.Remove asChild>
      <button
        type="button"
        className="aui-attachment-chip-remove"
        aria-label="Remove file"
        onPointerDown={(event) => event.stopPropagation()}
      >
        <CloseActionIcon className="aui-attachment-remove-icon size-3" />
      </button>
    </AttachmentPrimitive.Remove>
  );
};

export const UserMessageAttachments: FC = () => {
  return (
    <div className="aui-user-message-attachments flex w-full flex-row flex-wrap justify-start gap-1.5 empty:hidden">
      <MessagePrimitive.Attachments>
        {() => <AttachmentUI />}
      </MessagePrimitive.Attachments>
    </div>
  );
};

export const ComposerAttachments: FC = () => {
  return (
    <div className="aui-composer-attachments flex w-full flex-row flex-wrap items-center gap-1.5 overflow-x-auto empty:hidden">
      <ComposerPrimitive.Attachments>
        {() => <AttachmentUI />}
      </ComposerPrimitive.Attachments>
    </div>
  );
};

export const ComposerAddAttachment: FC = () => {
  return (
    <ComposerPrimitive.AddAttachment asChild>
      <TooltipIconButton
        tooltip="Add Attachment"
        side="bottom"
        variant="ghost"
        size="icon"
        className="aui-composer-add-attachment text-muted-foreground hover:text-foreground size-7"
        aria-label="Add Attachment"
      >
        <PlusActionIcon className="aui-attachment-add-icon size-3.5" />
      </TooltipIconButton>
    </ComposerPrimitive.AddAttachment>
  );
};
