import { create } from 'zustand';
import { User, USERS } from '../data/mockData';

interface AppState {
  currentUser: User;
  setCurrentUser: (user: User) => void;
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  toggleSidebar: () => void;
}

export const useAppStore = create<AppState>()((set) => ({
  currentUser: USERS[0], // Default: admin
  setCurrentUser: (user) => set({ currentUser: user }),
  sidebarOpen: true,
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
}));