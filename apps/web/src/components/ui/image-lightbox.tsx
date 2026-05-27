/**
 * 基于 Yet Another React Lightbox 的统一图片预览封装。
 *
 * 设计目标：
 * - 单图入口仍保持简单点击预览
 * - 多图入口可以直接带底部缩略图条
 * - 保持现有 import 路径稳定，避免全仓改名
 */

import { useEffect, useMemo, useState } from "react";
import type { ImgHTMLAttributes } from "react";
import Lightbox, { type SlideImage } from "yet-another-react-lightbox";
import Counter from "yet-another-react-lightbox/plugins/counter";
import Thumbnails from "yet-another-react-lightbox/plugins/thumbnails";
import Zoom from "yet-another-react-lightbox/plugins/zoom";
import "yet-another-react-lightbox/styles.css";
import "yet-another-react-lightbox/plugins/counter.css";
import "yet-another-react-lightbox/plugins/thumbnails.css";
import { cn } from "@/lib/utils";

export interface ImageLightboxSlide extends SlideImage {
  thumbnail?: string;
}

interface ImageLightboxProps
  extends Omit<ImgHTMLAttributes<HTMLImageElement>, "src" | "alt"> {
  src: string;
  alt?: string;
  className?: string;
  triggerClassName?: string;
  slides?: readonly ImageLightboxSlide[];
  startIndex?: number;
  wrapElement?: "div" | "span";
  zoomMargin?: number;
  zoomable?: boolean;
}

export interface ImageLightboxViewerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  slides: readonly ImageLightboxSlide[];
  startIndex?: number;
  zoomMargin?: number;
  zoomable?: boolean;
}

function normalizeSlides(
  src: string,
  alt?: string,
  slides?: readonly ImageLightboxSlide[],
): readonly ImageLightboxSlide[] {
  if (slides && slides.length > 0) {
    return slides;
  }

  return [
    {
      src,
      alt,
      thumbnail: src,
    },
  ];
}

function clampIndex(index: number, size: number): number {
  if (size <= 0) {
    return 0;
  }
  return Math.min(Math.max(index, 0), size - 1);
}

export function ImageLightbox({
  src,
  alt,
  className,
  triggerClassName,
  slides,
  startIndex = 0,
  wrapElement = "span",
  zoomMargin = 40,
  zoomable = true,
  draggable = false,
  ...imgProps
}: ImageLightboxProps) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(startIndex);

  const gallerySlides = useMemo(
    () => normalizeSlides(src, alt, slides),
    [alt, slides, src],
  );

  const initialIndex = clampIndex(startIndex, gallerySlides.length);
  const Wrapper = wrapElement;

  const openLightbox = () => {
    setActiveIndex(initialIndex);
    setOpen(true);
  };

  return (
    <>
      <Wrapper className="inline-block align-top">
        <button
          type="button"
          onClick={openLightbox}
          className={cn(
            "group inline-flex cursor-zoom-in overflow-hidden rounded-[inherit] bg-transparent p-0 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
            triggerClassName,
          )}
          title={alt ? `查看大图：${alt}` : "查看大图"}
        >
          <img
            {...imgProps}
            src={src}
            alt={alt}
            className={cn("select-none", className)}
            draggable={draggable}
          />
        </button>
      </Wrapper>

      <ImageLightboxViewer
        open={open}
        onOpenChange={setOpen}
        slides={gallerySlides}
        startIndex={activeIndex}
        zoomMargin={zoomMargin}
        zoomable={zoomable}
      />
    </>
  );
}

export function ImageLightboxViewer({
  open,
  onOpenChange,
  slides,
  startIndex = 0,
  zoomMargin = 40,
  zoomable = true,
}: ImageLightboxViewerProps) {
  const [activeIndex, setActiveIndex] = useState(startIndex);
  const thumbnailsEnabled = slides.length > 1;
  const plugins = useMemo(() => {
    const basePlugins = thumbnailsEnabled ? [Counter, Thumbnails] : [Counter];
    return zoomable ? [...basePlugins, Zoom] : basePlugins;
  }, [thumbnailsEnabled, zoomable]);

  useEffect(() => {
    if (open) {
      setActiveIndex(clampIndex(startIndex, slides.length));
    }
  }, [open, slides.length, startIndex]);

  if (slides.length === 0) {
    return null;
  }

  return (
    <Lightbox
      open={open}
      close={() => onOpenChange(false)}
      index={activeIndex}
      slides={slides}
      plugins={plugins}
      className="aiasys-gallery-lightbox"
      controller={{
        closeOnBackdropClick: true,
      }}
      carousel={{
        finite: slides.length <= 1,
        imageFit: "contain",
        padding: `${zoomMargin}px`,
        spacing: "6%",
      }}
      zoom={
        zoomable
          ? {
              maxZoomPixelRatio: 3,
              scrollToZoom: true,
            }
          : undefined
      }
      counter={{
        container: {
          style: {
            top: 18,
            left: 20,
          },
        },
      }}
      thumbnails={{
        position: "bottom",
        width: 72,
        height: 56,
        border: 0,
        borderRadius: 16,
        padding: 0,
        gap: 12,
        vignette: false,
        showToggle: thumbnailsEnabled,
        hidden: false,
        imageFit: "cover",
      }}
      labels={{
        Close: "关闭",
        Next: "下一张",
        Previous: "上一张",
        "Zoom in": "放大",
        "Zoom out": "缩小",
        "Show thumbnails": "显示缩略图",
        "Hide thumbnails": "隐藏缩略图",
      }}
      on={{
        view: ({ index: nextIndex }) => {
          setActiveIndex(nextIndex);
        },
      }}
      render={{
        iconClose: () => <span className="text-lg leading-none">×</span>,
      }}
      styles={{
        root: {
          "--yarl__portal_zindex": 80,
        },
      }}
      toolbar={{
        buttons: ["close"],
      }}
      animation={{
        fade: 220,
        swipe: 280,
      }}
      noScroll={{
        disabled: false,
      }}
    />
  );
}
