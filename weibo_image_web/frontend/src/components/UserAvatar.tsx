const WHITE_PLACEHOLDER =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='1' height='1'%3E%3Crect fill='%23eee' width='1' height='1'/%3E%3C/svg%3E";

interface UserAvatarProps {
  uid: string;
  size?: number;
  className?: string;
}

export default function UserAvatar({ uid, size = 32, className = "" }: UserAvatarProps) {
  return (
    <img
      className={`rounded-full object-cover bg-[#eee] shrink-0 ${className}`}
      src={`/media/${encodeURIComponent(uid)}/user_avatar.jpg`}
      alt=""
      width={size}
      height={size}
      onError={(e) => {
        e.currentTarget.src = WHITE_PLACEHOLDER;
        e.currentTarget.onerror = null;
      }}
    />
  );
}
