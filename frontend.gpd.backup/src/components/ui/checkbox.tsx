import React from 'react';
import clsx from 'clsx';

interface CheckboxProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export const Checkbox = React.forwardRef<HTMLInputElement, CheckboxProps>(
  ({ label, error, className, ...props }, ref) => {
    return (
      <div className="flex items-start">
        <input
          ref={ref}
          type="checkbox"
          className={clsx(
            'w-4 h-4 mt-1 rounded border-gray-300',
            'focus:ring-2 focus:ring-blue-500 focus:ring-offset-0',
            'cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed',
            'accent-blue-600',
            error && 'border-red-500',
            className
          )}
          {...props}
        />
        {label && (
          <label className="ml-2 text-sm text-gray-700 cursor-pointer flex-1">
            {label}
            {props.required && <span className="text-red-500 ml-1">*</span>}
          </label>
        )}
        {error && <p className="mt-1 text-sm text-red-500">{error}</p>}
      </div>
    );
  }
);

Checkbox.displayName = 'Checkbox';
