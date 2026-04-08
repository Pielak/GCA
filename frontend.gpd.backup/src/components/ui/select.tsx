import React, { createContext, useContext, useState } from 'react';
import clsx from 'clsx';
import { ChevronDown } from 'lucide-react';

interface SelectContextType {
  isOpen: boolean;
  setIsOpen: (open: boolean) => void;
  value: string | undefined;
  setValue: (value: string) => void;
}

const SelectContext = createContext<SelectContextType | undefined>(undefined);

const useSelectContext = () => {
  const context = useContext(SelectContext);
  if (!context) {
    throw new Error('Select components must be used within a Select component');
  }
  return context;
};

interface SelectProps {
  value?: string;
  onValueChange?: (value: string) => void;
  children: React.ReactNode;
}

export const Select = ({ value, onValueChange, children }: SelectProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const [internalValue, setInternalValue] = useState(value);

  const handleValueChange = (newValue: string) => {
    setInternalValue(newValue);
    onValueChange?.(newValue);
    setIsOpen(false);
  };

  return (
    <SelectContext.Provider
      value={{
        isOpen,
        setIsOpen,
        value: internalValue,
        setValue: handleValueChange,
      }}
    >
      <div className="relative w-full">{children}</div>
    </SelectContext.Provider>
  );
};

interface SelectTriggerProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  children: React.ReactNode;
}

export const SelectTrigger = React.forwardRef<HTMLButtonElement, SelectTriggerProps>(
  ({ children, className, ...props }, ref) => {
    const { isOpen, setIsOpen } = useSelectContext();

    return (
      <button
        ref={ref}
        onClick={() => setIsOpen(!isOpen)}
        className={clsx(
          'w-full px-3 py-2 border border-gray-300 rounded-lg',
          'bg-white text-gray-900 text-left',
          'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent',
          'flex items-center justify-between',
          className
        )}
        {...props}
      >
        <span>{children}</span>
        <ChevronDown className={clsx('w-4 h-4 transition-transform', isOpen && 'transform rotate-180')} />
      </button>
    );
  }
);

SelectTrigger.displayName = 'SelectTrigger';

interface SelectValueProps {
  placeholder?: string;
}

export const SelectValue = ({ placeholder = 'Select an option...' }: SelectValueProps) => {
  const { value } = useSelectContext();
  return <span>{value || placeholder}</span>;
};

interface SelectContentProps {
  children: React.ReactNode;
}

export const SelectContent = ({ children }: SelectContentProps) => {
  const { isOpen } = useSelectContext();

  if (!isOpen) return null;

  return (
    <div className="absolute z-50 w-full mt-1 bg-white border border-gray-300 rounded-lg shadow-lg">
      <div className="max-h-60 overflow-y-auto">{children}</div>
    </div>
  );
};

interface SelectItemProps {
  value: string;
  children: React.ReactNode;
}

export const SelectItem = ({ value, children }: SelectItemProps) => {
  const { value: selectedValue, setValue } = useSelectContext();

  return (
    <button
      onClick={() => setValue(value)}
      className={clsx(
        'w-full px-3 py-2 text-left hover:bg-blue-50',
        selectedValue === value && 'bg-blue-100 text-blue-900 font-medium'
      )}
    >
      {children}
    </button>
  );
};
