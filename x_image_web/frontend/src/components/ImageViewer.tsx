import { useEffect, useCallback } from "react";

interface ImageViewerProps {
  images: string[];
  index: number;
  onClose: () => void;
  onNavigate: (index: number) => void;
}

export default function ImageViewer({ images, index, onClose, onNavigate }: ImageViewerProps) {
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === "Escape") onClose();
    if (e.key === "ArrowLeft" && index > 0) onNavigate(index - 1);
    if (e.key === "ArrowRight" && index < images.length - 1) onNavigate(index + 1);
  }, [index, images.length, onClose, onNavigate]);

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  return (
    <div
      className="fixed inset-0 z-[200] bg-black/95 flex items-center justify-center"
      onClick={onClose}
    >
      {/* Close button */}
      <button
        className="absolute top-4 right-4 w-10 h-10 rounded-full bg-white/10 border border-white/20 text-white
                   flex items-center justify-center cursor-pointer hover:bg-white/20 transition-colors z-10"
        onClick={onClose}
      >
        ✕
      </button>

      {/* Counter */}
      <div className="absolute top-4 left-4 text-white/70 text-sm bg-black/50 px-3 py-1 rounded-full">
        {index + 1} / {images.length}
      </div>

      {/* Image */}
      <img
        src={images[index]}
        alt=""
        className="max-w-[90vw] max-h-[90vh] object-contain rounded-lg"
        onClick={(e) => e.stopPropagation()}
      />

      {/* Navigation arrows */}
      {index > 0 && (
        <button
          className="absolute left-4 top-1/2 -translate-y-1/2 w-12 h-12 rounded-full bg-white/10 border border-white/20
                     text-white flex items-center justify-center cursor-pointer hover:bg-white/20 transition-colors text-xl"
          onClick={(e) => { e.stopPropagation(); onNavigate(index - 1); }}
        >
          ‹
        </button>
      )}
      {index < images.length - 1 && (
        <button
          className="absolute right-4 top-1/2 -translate-y-1/2 w-12 h-12 rounded-full bg-white/10 border border-white/20
                     text-white flex items-center justify-center cursor-pointer hover:bg-white/20 transition-colors text-xl"
          onClick={(e) => { e.stopPropagation(); onNavigate(index + 1); }}
        >
          ›
        </button>
      )}
    </div>
  );
}
