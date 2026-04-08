/**
 * Breadcrumb — Auto-generated layout component
 * Generated: 2026-04-03
 *
 * Navigation breadcrumb trail
 */

import React, { FC, ReactNode } from 'react';
import { ChevronRight } from 'lucide-react';
import clsx from 'clsx';

export interface BreadcrumbItem {
  label: string;
  href?: string;
  isCurrent?: boolean;
}

export interface BreadcrumbProps {
  items: BreadcrumbItem[];
  separator?: ReactNode;
  maxItems?: number;
  className?: string;
}

/**
 * Breadcrumb Component
 *
 * Features:
 * - Navigation context trail
 * - Truncation support (max items)
 * - Custom separator support
 * - Current page indicator
 *
 * Accessibility:
 * - role="navigation"
 * - aria-label="Breadcrumb"
 * - aria-current="page" on last item
 * - Proper list semantics
 */
export const Breadcrumb: FC<BreadcrumbProps> = ({
  items,
  separator = <ChevronRight size={16} />,
  maxItems = 0,
  className,
}) => {
  let displayItems = items;

  // Handle max items truncation
  if (maxItems > 0 && items.length > maxItems) {
    displayItems = [
      items[0],
      { label: '...', isCurrent: false },
      ...items.slice(-(maxItems - 1)),
    ];
  }

  return (
    <nav
      role="navigation"
      aria-label="Breadcrumb"
      className={clsx('py-4 px-6', className)}
    >
      <ol className="flex items-center flex-wrap gap-2">
        {displayItems.map((item, idx) => (
          <li key={idx} className="flex items-center gap-2">
            {item.href && !item.isCurrent ? (
              <a
                href={item.href}
                className={clsx(
                  'text-sm text-cyan-400 hover:text-cyan-300 transition-colors',
                  'focus:outline-none focus:ring-2 focus:ring-cyan-500 rounded px-1'
                )}
              >
                {item.label}
              </a>
            ) : (
              <span
                className={clsx(
                  'text-sm',
                  item.isCurrent ? 'text-white font-medium' : 'text-gray-400'
                )}
                aria-current={item.isCurrent ? 'page' : undefined}
              >
                {item.label}
              </span>
            )}

            {idx < displayItems.length - 1 && (
              <span className="text-gray-600 flex items-center">{separator}</span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
};

export default Breadcrumb;
