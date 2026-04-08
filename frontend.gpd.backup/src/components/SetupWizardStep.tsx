/**
 * Setup Wizard Step Component
 *
 * Reusable component for each step of the setup wizard.
 * Handles heading, description, form fields, and validation messages.
 */

import React, { ReactNode } from 'react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { AlertCircle, CheckCircle2, Loader } from 'lucide-react';

interface SetupWizardStepProps {
  stepNumber: number;
  title: string;
  description: string;
  children: ReactNode;
  isLoading?: boolean;
  error?: string | null;
  success?: boolean;
  successMessage?: string;
}

export function SetupWizardStep({
  stepNumber,
  title,
  description,
  children,
  isLoading = false,
  error = null,
  success = false,
  successMessage = 'Validation successful',
}: SetupWizardStepProps) {
  return (
    <div className="space-y-6">
      {/* Step Header */}
      <div className="border-b pb-6">
        <div className="flex items-center gap-4 mb-2">
          <div className="flex items-center justify-center w-10 h-10 rounded-full bg-blue-100 text-blue-700 font-semibold">
            {stepNumber}
          </div>
          <div>
            <h2 className="text-2xl font-bold text-gray-900">{title}</h2>
            <p className="text-gray-600 mt-1">{description}</p>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="space-y-4">
        {/* Error Alert */}
        {error && (
          <Alert variant="destructive" className="border-red-200 bg-red-50">
            <AlertCircle className="h-4 w-4 text-red-600" />
            <AlertDescription className="text-red-700 ml-2">{error}</AlertDescription>
          </Alert>
        )}

        {/* Success Alert */}
        {success && (
          <Alert className="border-green-200 bg-green-50">
            <CheckCircle2 className="h-4 w-4 text-green-600" />
            <AlertDescription className="text-green-700 ml-2">{successMessage}</AlertDescription>
          </Alert>
        )}

        {/* Loading Indicator */}
        {isLoading && (
          <div className="flex items-center gap-2 text-blue-600 py-2">
            <Loader className="h-4 w-4 animate-spin" />
            <span>Validating...</span>
          </div>
        )}

        {/* Form Content */}
        <div className={isLoading ? 'opacity-50 pointer-events-none' : ''}>{children}</div>
      </div>
    </div>
  );
}

export default SetupWizardStep;
