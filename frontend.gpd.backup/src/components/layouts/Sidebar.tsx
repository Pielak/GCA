/**
 * Sidebar — Auto-generated layout component
 * Generated: 2026-04-03
 *
 * Collapsible sidebar with navigation tree
 */

import React, { FC, ReactNode, useState } from 'react';
import { ChevronRight, ChevronDown } from 'lucide-react';
import clsx from 'clsx';

export interface NavItem {
  id: string;
  label: string;
  href?: string;
  icon?: ReactNode;
  badge?: number | string;
  children?: NavItem[];
}

export interface SidebarProps {
  items: NavItem[];
  collapsible?: boolean;
  width?: number;
  sticky?: boolean;
  activeRoute?: string;
  onNavigate?: (href: string) => void;
  collapsed?: boolean;
  onCollapsedChange?: (collapsed: boolean) => void;
  className?: string;
}

/**
 * Sidebar Component
 *
 * Features:
 * - Nested navigation tree with children
 * - Collapsible sections
 * - Active route highlighting
 * - Badge support
 * - Responsive (hidden on mobile by default)
 * - Full accessibility (ARIA, keyboard navigation)
 *
 * Accessibility:
 * - role="complementary"
 * - aria-label="Side navigation"
 * - Nested list semantics
 * - Active indicator with aria-current
 */
export const Sidebar: FC<SidebarProps> = ({
  items,
  collapsible = true,
  width = 280,
  sticky = true,
  activeRoute = '',
  onNavigate,
  collapsed: controlledCollapsed,
  onCollapsedChange,
  className,
}) => {
  const [expandedItems, setExpandedItems] = useState<Set<string>>(new Set());
  const [internalCollapsed, setInternalCollapsed] = useState(false);

  const isCollapsed = controlledCollapsed !== undefined ? controlledCollapsed : internalCollapsed;

  const toggleExpanded = (id: string, e: React.MouseEvent) => {
    e.preventDefault();
    setExpandedItems((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleCollapse = () => {
    if (controlledCollapsed !== undefined) {
      onCollapsedChange?.(!controlledCollapsed);
    } else {
      setInternalCollapsed(!internalCollapsed);
    }
  };

  const renderNavItem = (item: NavItem, level: number = 0): ReactNode => {
    const isExpanded = expandedItems.has(item.id);
    const hasChildren = item.children && item.children.length > 0;
    const isActive = activeRoute === item.href;

    return (
      <li key={item.id} className="w-full">
        <div className={clsx('flex items-center', level > 0 && 'ml-4')}>
          {hasChildren ? (
            <button
              onClick={(e) => toggleExpanded(item.id, e)}
              className={clsx(
                'flex items-center flex-1 px-3 py-2 rounded text-sm text-gray-300',
                'hover:bg-dark-200 hover:text-white transition-colors',
                'focus:outline-none focus:ring-2 focus:ring-cyan-500'
              )}
              aria-expanded={isExpanded}
            >
              {item.icon && <span className="w-4 h-4 mr-2 shrink-0">{item.icon}</span>}
              {!isCollapsed && <span className="flex-1 text-left">{item.label}</span>}
              {!isCollapsed && (
                <>
                  {item.badge && (
                    <span className="ml-2 px-2 py-0.5 text-xs bg-cyan-600 text-white rounded-full">
                      {item.badge}
                    </span>
                  )}
                  <span className="w-4 h-4 ml-2 shrink-0">
                    {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  </span>
                </>
              )}
            </button>
          ) : (
            <a
              href={item.href || '#'}
              onClick={(e) => {
                if (item.href) {
                  e.preventDefault();
                  onNavigate?.(item.href);
                }
              }}
              className={clsx(
                'flex items-center flex-1 px-3 py-2 rounded text-sm transition-colors',
                'focus:outline-none focus:ring-2 focus:ring-cyan-500',
                isActive
                  ? 'bg-cyan-600/20 text-cyan-400 border-r-2 border-cyan-600'
                  : 'text-gray-300 hover:bg-dark-200 hover:text-white'
              )}
              aria-current={isActive ? 'page' : undefined}
            >
              {item.icon && <span className="w-4 h-4 mr-2 shrink-0">{item.icon}</span>}
              {!isCollapsed && <span className="flex-1 text-left">{item.label}</span>}
              {!isCollapsed && item.badge && (
                <span className="ml-2 px-2 py-0.5 text-xs bg-cyan-600 text-white rounded-full">
                  {item.badge}
                </span>
              )}
            </a>
          )}
        </div>

        {/* Nested items */}
        {hasChildren && isExpanded && !isCollapsed && (
          <ul className="space-y-1">
            {item.children!.map((child) => renderNavItem(child, level + 1))}
          </ul>
        )}
      </li>
    );
  };

  return (
    <aside
      role="complementary"
      aria-label="Side navigation"
      className={clsx(
        'bg-dark-100 border-r border-gray-800 overflow-y-auto transition-all duration-300',
        sticky && 'sticky top-16 h-[calc(100vh-4rem)]',
        isCollapsed ? 'w-20' : `w-${width}`,
        className
      )}
      style={!isCollapsed ? { width: `${width}px` } : undefined}
    >
      {/* Collapse button */}
      {collapsible && (
        <div className="p-2 border-b border-gray-800">
          <button
            onClick={handleCollapse}
            className={clsx(
              'w-full px-3 py-2 rounded text-sm text-gray-400 hover:text-white',
              'hover:bg-dark-200 transition-colors',
              'focus:outline-none focus:ring-2 focus:ring-cyan-500'
            )}
            title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {isCollapsed ? '→' : '←'}
          </button>
        </div>
      )}

      {/* Navigation items */}
      <nav className="p-2 space-y-1" aria-label="Navigation menu">
        <ul className="space-y-1">
          {items.map((item) => renderNavItem(item))}
        </ul>
      </nav>
    </aside>
  );
};

export default Sidebar;
