import { useEffect, useRef, type ReactNode } from 'react';
import { X } from 'lucide-react';

interface DialogProps {
  title: string;
  onClose: () => void;
  children: ReactNode;
  className?: string;
}

export function Dialog({ title, onClose, children, className = '' }: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    dialog.showModal();
    return () => dialog.close();
  }, []);

  return (
    <dialog
      ref={ref}
      className={`dialog ${className}`}
      aria-labelledby="dialog-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="dialog-header">
        <h2 id="dialog-title">{title}</h2>
        <button className="icon-button" onClick={onClose} aria-label="Đóng">
          <X size={20} />
        </button>
      </div>
      <div className="dialog-body">{children}</div>
    </dialog>
  );
}
