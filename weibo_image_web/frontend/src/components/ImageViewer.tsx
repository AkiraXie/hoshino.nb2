import { useEffect, useCallback, useRef, useState } from "react";

interface ImageViewerProps {
  images: string[];
  index: number;
  onClose: () => void;
  onChange: (index: number) => void;
}

export default function ImageViewer({
  images,
  index,
  onClose,
  onChange,
}: ImageViewerProps) {
  const [dragY, setDragY] = useState(0);
  const [dragX, setDragX] = useState(0);
  const [isSwiping, setIsSwiping] = useState(false);
  const [isTransitioning, setIsTransitioning] = useState(false);

  const startX = useRef(0);
  const startY = useRef(0);
  const currentImageSrc = images[index];

  const triggerImageChange = useCallback((newIndex: number) => {
    setIsTransitioning(true);
    setTimeout(() => {
      onChange(newIndex);
      setIsTransitioning(false);
    }, 150);
  }, [onChange]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft" && index > 0) {
        triggerImageChange(index - 1);
      }
      if (e.key === "ArrowRight" && index < images.length - 1) {
        triggerImageChange(index + 1);
      }
    },
    [index, images, onClose, triggerImageChange]
  );

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "";
    };
  }, [handleKeyDown]);

  const handleTouchStart = (e: React.TouchEvent) => {
    startX.current = e.touches[0].clientX;
    startY.current = e.touches[0].clientY;
    setIsSwiping(true);
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    if (!isSwiping) return;
    const currentX = e.touches[0].clientX;
    const currentY = e.touches[0].clientY;
    const diffX = currentX - startX.current;
    const diffY = currentY - startY.current;
    if (Math.abs(diffY) > Math.abs(diffX)) {
      setDragY(diffY);
      setDragX(0);
    } else {
      setDragX(diffX);
      setDragY(0);
    }
  };

  const handleTouchEnd = () => {
    setIsSwiping(false);
    if (dragY > 120) {
      onClose();
      return;
    }
    if (dragX > 70 && index > 0) {
      triggerImageChange(index - 1);
    } else if (dragX < -70 && index < images.length - 1) {
      triggerImageChange(index + 1);
    }
    setDragY(0);
    setDragX(0);
  };

  const dragRatio = Math.min(Math.abs(dragY) / 350, 1);
  const dragOpacity = 1 - dragRatio * 0.7;
  const scale = 1 - dragRatio * 0.15;

  return (
    <div
      className="fixed inset-0 z-[1000] flex items-center justify-center"
      style={{ backgroundColor: `rgba(9, 13, 22, ${dragOpacity * 0.95})` }}
      onClick={onClose}
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
    >
      {/* Ambient backdrop */}
      <div
        className="ambient-backdrop"
        style={{
          backgroundImage: `url(${currentImageSrc})`,
          opacity: dragOpacity * 0.45,
        }}
      />

      <div
        style={{
          transform: `translate(${dragX}px, ${dragY}px) scale(${scale})`,
          opacity: isTransitioning ? 0 : 1,
          transition: isSwiping ? "none" : "transform 0.3s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.2s ease",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <img
          className="max-w-[92vw] max-h-[92vh] object-contain select-none"
          src={currentImageSrc}
          alt=""
          decoding="async"
        />
      </div>

      {/* Close button */}
      <button
        className="absolute top-4 right-4 bg-white/15 border-none text-white text-[22px] w-10 h-10 rounded-full cursor-pointer flex items-center justify-center hover:bg-white/30 max-md:w-[34px] max-md:h-[34px] max-md:text-lg max-md:top-2.5 max-md:right-2.5"
        onClick={onClose}
        title="关闭 (Esc)"
      >
        <svg viewBox="0 0 24 24" width="20" height="24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <line x1="18" y1="6" x2="6" y2="18"></line>
          <line x1="6" y1="6" x2="18" y2="18"></line>
        </svg>
      </button>

      {/* Nav arrows */}
      {index > 0 && (
        <button
          className="absolute top-1/2 -translate-y-1/2 left-4 bg-white/15 border-none text-white text-[28px] w-12 h-12 rounded-full cursor-pointer flex items-center justify-center hover:bg-white/30 max-md:w-9 max-md:h-9 max-md:text-[22px] max-md:left-2"
          onClick={(e) => {
            e.stopPropagation();
            triggerImageChange(index - 1);
          }}
          title="上一张 (←)"
        >
          <svg viewBox="0 0 24 24" width="24" height="28" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="15 18 9 12 15 6"></polyline>
          </svg>
        </button>
      )}

      {index < images.length - 1 && (
        <button
          className="absolute top-1/2 -translate-y-1/2 right-4 bg-white/15 border-none text-white text-[28px] w-12 h-12 rounded-full cursor-pointer flex items-center justify-center hover:bg-white/30 max-md:w-9 max-md:h-9 max-md:text-[22px] max-md:right-2"
          onClick={(e) => {
            e.stopPropagation();
            triggerImageChange(index + 1);
          }}
          title="下一张 (→)"
        >
          <svg viewBox="0 0 24 24" width="24" height="28" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="9 18 15 12 9 6"></polyline>
          </svg>
        </button>
      )}

      {/* Counter */}
      <div className="absolute bottom-5 text-white/70 text-sm" style={{ opacity: dragOpacity }}>
        <span>{index + 1}</span>
        <span> / </span>
        <span>{images.length}</span>
      </div>
    </div>
  );
}
