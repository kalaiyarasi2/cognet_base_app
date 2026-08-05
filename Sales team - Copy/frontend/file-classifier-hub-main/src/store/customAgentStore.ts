import { create } from 'zustand';

export interface CustomField {
  name: string;
  type: string;
  description: string;
}

interface CustomAgentState {
  isOpen: boolean;
  activeNodeId: string | null;
  customFields: CustomField[];
  openDrawer: (nodeId: string, fields: CustomField[]) => void;
  closeDrawer: () => void;
}

export const useCustomAgentStore = create<CustomAgentState>((set) => ({
  isOpen: false,
  activeNodeId: null,
  customFields: [],
  openDrawer: (nodeId, fields) => set({ isOpen: true, activeNodeId: nodeId, customFields: fields }),
  closeDrawer: () => set({ isOpen: false, activeNodeId: null, customFields: [] }),
}));
