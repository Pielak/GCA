import React from 'react';
import clsx from 'clsx';
import { AlertCircle, CheckCircle2, Info, XCircle } from 'lucide-react';

interface AlertProps extends React.HTMLAttributes<HTMLDivElement> {
  type?: 'success' | 'error' | 'warning' | 'info';
  variant?: 'default' | 'destructive';
  title?: string;
  onClose?: () => void;
  children: React.ReactNode;
}

export const Alert = React.forwardRef<HTMLDivElement, AlertProps>(
  ({ type, variant, title, onClose, className, children, ...props }, ref) => {
    // Support both type and variant props
    const alertType = variant === 'destructive' ? 'error' : type || 'info';

    const styles = {
      success: {
        bg: 'bg-green-50',
        border: 'border-green-200',
        text: 'text-green-800',
        icon: CheckCircle2,
      },
      error: {
        bg: 'bg-red-50',
        border: 'border-red-200',
        text: 'text-red-800',
        icon: XCircle,
      },
      warning: {
        bg: 'bg-yellow-50',
        border: 'border-yellow-200',
        text: 'text-yellow-800',
        icon: AlertCircle,
      },
      info: {
        bg: 'bg-blue-50',
        border: 'border-blue-200',
        text: 'text-blue-800',
        icon: Info,
      },
    };

    const style = styles[alertType];
    const IconComponent = style.icon;

    return (
      <div ref={ref} className={clsx('p-4 border rounded-lg flex items-start', style.bg, style.border, className)} {...props}>
        <IconComponent className={clsx('w-5 h-5 mt-0.5 mr-3 flex-shrink-0', style.text)} />
        <div className="flex-1">
          {title && <h4 className={clsx('font-medium mb-1', style.text)}>{title}</h4>}
          <div className={clsx('text-sm', style.text)}>{children}</div>
        </div>
        {onClose && (
          <button onClick={onClose} className={clsx('ml-3 text-xl font-bold', style.text)}>
            ×
          </button>
        )}
      </div>
    );
  }
);

Alert.displayName = 'Alert';

interface AlertDescriptionProps extends React.HTMLAttributes<HTMLParagraphElement> {
  children: React.ReactNode;
}

export const AlertDescription = React.forwardRef<HTMLParagraphElement, AlertDescriptionProps>(
  ({ className, children, ...props }, ref) => (
    <p ref={ref} className={clsx('text-sm', className)} {...props}>
      {children}
    </p>
  )
);

AlertDescription.displayName = 'AlertDescription';
