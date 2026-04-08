/**
 * Pagination — Auto-generated layout component
 * Generated: 2026-04-03
 *
 * Pagination controls for lists and tables
 */

import React, { FC } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import clsx from 'clsx';

export interface PaginationProps {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  maxVisible?: number;
  className?: string;
  disabled?: boolean;
}

/**
 * Pagination Component
 *
 * Features:
 * - Page number display
 * - Previous/Next navigation
 * - Ellipsis for large page counts
 * - Responsive (simplified on mobile)
 *
 * Accessibility:
 * - role="navigation"
 * - aria-label="Pagination"
 * - aria-current="true" on active page
 * - Disabled state for prev/next
 */
export const Pagination: FC<PaginationProps> = ({
  currentPage,
  totalPages,
  onPageChange,
  maxVisible = 5,
  className,
  disabled = false,
}) => {
  // Calculate page numbers to display
  let pageNumbers: (number | string)[] = [];

  if (totalPages <= maxVisible) {
    // Show all pages
    pageNumbers = Array.from({ length: totalPages }, (_, i) => i + 1);
  } else {
    // Show first page, last page, current page, and neighbors
    const halfVisible = Math.floor(maxVisible / 2);
    let start = Math.max(1, currentPage - halfVisible);
    let end = Math.min(totalPages, start + maxVisible - 1);

    // Adjust if we're near the end
    if (end - start + 1 < maxVisible) {
      start = Math.max(1, end - maxVisible + 1);
    }

    // Always show first page
    if (start > 1) {
      pageNumbers.push(1);
      if (start > 2) pageNumbers.push('...');
    }

    // Add range
    for (let i = start; i <= end; i++) {
      pageNumbers.push(i);
    }

    // Always show last page
    if (end < totalPages) {
      if (end < totalPages - 1) pageNumbers.push('...');
      pageNumbers.push(totalPages);
    }
  }

  const handlePrevious = () => {
    if (currentPage > 1 && !disabled) {
      onPageChange(currentPage - 1);
    }
  };

  const handleNext = () => {
    if (currentPage < totalPages && !disabled) {
      onPageChange(currentPage + 1);
    }
  };

  return (
    <nav
      role="navigation"
      aria-label="Pagination"
      className={clsx('flex items-center justify-center gap-2 py-4', className)}
    >
      {/* Previous Button */}
      <button
        onClick={handlePrevious}
        disabled={currentPage === 1 || disabled}
        className={clsx(
          'p-2 rounded border transition-colors',
          'focus:outline-none focus:ring-2 focus:ring-cyan-500',
          currentPage === 1 || disabled
            ? 'border-gray-700 text-gray-600 cursor-not-allowed'
            : 'border-gray-700 text-gray-400 hover:text-white hover:border-gray-600'
        )}
        aria-label="Previous page"
      >
        <ChevronLeft size={18} />
      </button>

      {/* Page Numbers - Desktop */}
      <div className="hidden sm:flex items-center gap-1">
        {pageNumbers.map((page, idx) => (
          <button
            key={idx}
            onClick={() => typeof page === 'number' && onPageChange(page)}
            disabled={page === '...' || disabled}
            className={clsx(
              'w-8 h-8 rounded text-sm transition-colors',
              'focus:outline-none focus:ring-2 focus:ring-cyan-500',
              page === currentPage
                ? 'bg-cyan-600 text-white'
                : page === '...'
                  ? 'text-gray-500 cursor-default'
                  : 'border border-gray-700 text-gray-400 hover:text-white hover:border-gray-600'
            )}
            aria-current={page === currentPage ? 'page' : undefined}
            aria-label={page === '...' ? 'More pages' : `Go to page ${page}`}
          >
            {page}
          </button>
        ))}
      </div>

      {/* Page Info - Mobile */}
      <div className="sm:hidden text-sm text-gray-400">
        {currentPage} / {totalPages}
      </div>

      {/* Next Button */}
      <button
        onClick={handleNext}
        disabled={currentPage === totalPages || disabled}
        className={clsx(
          'p-2 rounded border transition-colors',
          'focus:outline-none focus:ring-2 focus:ring-cyan-500',
          currentPage === totalPages || disabled
            ? 'border-gray-700 text-gray-600 cursor-not-allowed'
            : 'border-gray-700 text-gray-400 hover:text-white hover:border-gray-600'
        )}
        aria-label="Next page"
      >
        <ChevronRight size={18} />
      </button>
    </nav>
  );
};

export default Pagination;
