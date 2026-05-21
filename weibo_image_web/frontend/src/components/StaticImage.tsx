import { useEffect, useRef, useState } from "react";

const gifFrameCache = new Map<string, string>();

interface StaticImageProps extends React.ImgHTMLAttributes<HTMLImageElement> {
  src: string;
}

export default function StaticImage({ src, alt, className, loading, decoding, ...props }: StaticImageProps) {
  const isThumb = src.includes("/thumbnails/");

  if (isThumb) {
    return (
      <picture>
        <source srcSet={`${src}.webp`} type="image/webp" />
        <img
          src={`${src}.jpg`}
          alt={alt}
          className={className}
          loading={loading ?? "lazy"}
          decoding={decoding ?? "async"}
          {...props}
        />
      </picture>
    );
  }

  const isGif = src.split("?")[0].split("#")[0].toLowerCase().endsWith(".gif");

  if (!isGif) {
    return (
      <img
        src={src}
        alt={alt}
        className={className}
        loading={loading ?? "lazy"}
        decoding={decoding ?? "async"}
        {...props}
      />
    );
  }

  // ── GIF path: extract first frame via canvas ──
  const cachedDataUrl = gifFrameCache.get(src);
  const [staticSrc, setStaticSrc] = useState<string | null>(cachedDataUrl ?? null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const drawingRef = useRef(false);

  useEffect(() => {
    if (staticSrc) return;
    drawingRef.current = true;
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.decoding = "async";
    img.onload = () => {
      if (!drawingRef.current) return;
      const canvas = canvasRef.current;
      if (!canvas) return;
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      const ctx = canvas.getContext("2d");
      if (ctx) {
        ctx.drawImage(img, 0, 0);
        try {
          const dataUrl = canvas.toDataURL("image/jpeg");
          gifFrameCache.set(src, dataUrl);
          setStaticSrc(dataUrl);
        } catch {
          setStaticSrc(src);
        }
      }
    };
    img.onerror = () => {
      if (drawingRef.current) setStaticSrc(src);
    };
    img.src = src;
    return () => {
      drawingRef.current = false;
    };
  }, [src, staticSrc]);

  if (!staticSrc) {
    return (
      <>
        <canvas ref={canvasRef} style={{ display: "none" }} />
        <div
          className={className}
          style={{ background: "#e4e7eb", height: 380, ...props.style }}
          aria-label={alt || ""}
        />
      </>
    );
  }

  return (
    <>
      <canvas ref={canvasRef} style={{ display: "none" }} />
      <img
        src={staticSrc}
        alt={alt}
        className={className}
        loading={loading ?? "lazy"}
        decoding={decoding ?? "async"}
        {...props}
      />
    </>
  );
}
