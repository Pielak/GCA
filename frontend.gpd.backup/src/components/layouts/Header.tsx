/**
 * Header — Auto-generated layout component
 * Generated: 2026-04-03
 *
 * Navigation header with logo, menu, and user menu
 */

import React, { FC, ReactNode, useState } from 'react';
import { Menu, X, LogOut, Settings, User as UserIcon } from 'lucide-react';
import clsx from 'clsx';

export interface MenuItem {
  label: string;
  href: string;
  icon?: ReactNode;
  badge?: number;
}

export interface HeaderProps {
  logo?: string | ReactNode;
  menuItems?: MenuItem[];
  userMenu?: boolean;
  sticky?: boolean;
  darkMode?: boolean;
  userName?: string;
  onLogout?: () => void;
  className?: string;
}

/**
 * Header Component
 *
 * Features:
 * - Responsive navigation (hamburger on mobile)
 * - User menu dropdown
 * - Sticky positioning
 * - Dark mode support
 * - Full accessibility (ARIA, keyboard navigation)
 *
 * Accessibility:
 * - role="navigation"
 * - aria-label="Main navigation"
 * - Keyboard navigation (Tab, Enter, Escape)
 * - Focus management
 */
export const Header: FC<HeaderProps> = ({
  logo,
  menuItems = [],
  userMenu = true,
  sticky = true,
  darkMode = false,
  userName = 'User',
  onLogout,
  className,
}) => {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);

  const handleEscape = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      setMobileMenuOpen(false);
      setUserMenuOpen(false);
    }
  };

  return (
    <header
      role="navigation"
      aria-label="Main navigation"
      onKeyDown={handleEscape}
      className={clsx(
        'bg-dark-100 border-b border-gray-800 z-40',
        sticky && 'sticky top-0',
        className
      )}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-16">
          {/* Logo */}
          <div className="flex-shrink-0">
            {typeof logo === 'string' ? (
              <img src={logo} alt="Logo" className="h-8 w-auto" />
            ) : (
              <div className="text-xl font-bold text-white">{logo || 'Logo'}</div>
            )}
          </div>

          {/* Desktop Menu */}
          <nav
            className="hidden md:flex gap-6"
            aria-label="Main navigation items"
          >
            {menuItems.map((item, idx) => (
              <a
                key={idx}
                href={item.href}
                className="flex items-center gap-2 text-sm text-gray-300 hover:text-white transition-colors focus:outline-none focus:ring-2 focus:ring-cyan-500 rounded px-2 py-1"
              >
                {item.icon && <span className="w-4 h-4">{item.icon}</span>}
                <span>{item.label}</span>
                {item.badge && (
                  <span className="ml-1 px-2 py-0.5 text-xs bg-cyan-600 text-white rounded-full">
                    {item.badge}
                  </span>
                )}
              </a>
            ))}
          </nav>

          {/* Right side: User Menu + Mobile Toggle */}
          <div className="flex items-center gap-4">
            {/* User Menu (Desktop) */}
            {userMenu && (
              <div className="hidden sm:flex relative">
                <button
                  onClick={() => setUserMenuOpen(!userMenuOpen)}
                  className="flex items-center gap-2 text-sm text-gray-300 hover:text-white transition-colors focus:outline-none focus:ring-2 focus:ring-cyan-500 rounded px-3 py-2"
                  aria-haspopup="true"
                  aria-expanded={userMenuOpen}
                >
                  <UserIcon size={16} />
                  <span className="hidden sm:inline">{userName}</span>
                </button>

                {/* User Menu Dropdown */}
                {userMenuOpen && (
                  <div
                    className="absolute right-0 mt-12 w-48 bg-dark-200 border border-gray-700 rounded-lg shadow-xl"
                    role="menu"
                  >
                    <a
                      href="/profile"
                      className="flex items-center gap-2 px-4 py-2 text-sm text-gray-300 hover:bg-gray-800 transition-colors"
                      role="menuitem"
                    >
                      <UserIcon size={16} />
                      Profile
                    </a>
                    <a
                      href="/settings"
                      className="flex items-center gap-2 px-4 py-2 text-sm text-gray-300 hover:bg-gray-800 transition-colors"
                      role="menuitem"
                    >
                      <Settings size={16} />
                      Settings
                    </a>
                    <hr className="border-gray-700 my-1" />
                    <button
                      onClick={() => {
                        setUserMenuOpen(false);
                        onLogout?.();
                      }}
                      className="flex items-center gap-2 w-full px-4 py-2 text-sm text-red-400 hover:bg-gray-800 transition-colors text-left"
                      role="menuitem"
                    >
                      <LogOut size={16} />
                      Logout
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Mobile Menu Toggle */}
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="md:hidden inline-flex items-center justify-center p-2 rounded-md text-gray-400 hover:text-white hover:bg-dark-200 focus:outline-none focus:ring-2 focus:ring-cyan-500"
              aria-expanded={mobileMenuOpen}
              aria-controls="mobile-menu"
            >
              {mobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
            </button>
          </div>
        </div>

        {/* Mobile Menu */}
        {mobileMenuOpen && (
          <nav
            id="mobile-menu"
            className="md:hidden border-t border-gray-800 py-4 space-y-2"
            aria-label="Mobile navigation"
          >
            {menuItems.map((item, idx) => (
              <a
                key={idx}
                href={item.href}
                className="flex items-center gap-2 px-4 py-2 text-sm text-gray-300 hover:bg-dark-200 rounded transition-colors focus:outline-none focus:ring-2 focus:ring-cyan-500"
              >
                {item.icon && <span className="w-4 h-4">{item.icon}</span>}
                <span>{item.label}</span>
                {item.badge && (
                  <span className="ml-auto px-2 py-0.5 text-xs bg-cyan-600 text-white rounded-full">
                    {item.badge}
                  </span>
                )}
              </a>
            ))}

            {/* Mobile User Menu */}
            {userMenu && (
              <>
                <hr className="border-gray-700 my-2" />
                <a
                  href="/profile"
                  className="flex items-center gap-2 px-4 py-2 text-sm text-gray-300 hover:bg-dark-200 rounded transition-colors"
                >
                  <UserIcon size={16} />
                  Profile
                </a>
                <a
                  href="/settings"
                  className="flex items-center gap-2 px-4 py-2 text-sm text-gray-300 hover:bg-dark-200 rounded transition-colors"
                >
                  <Settings size={16} />
                  Settings
                </a>
                <button
                  onClick={() => {
                    setMobileMenuOpen(false);
                    onLogout?.();
                  }}
                  className="flex items-center gap-2 w-full px-4 py-2 text-sm text-red-400 hover:bg-dark-200 rounded transition-colors text-left"
                >
                  <LogOut size={16} />
                  Logout
                </button>
              </>
            )}
          </nav>
        )}
      </div>
    </header>
  );
};

export default Header;
