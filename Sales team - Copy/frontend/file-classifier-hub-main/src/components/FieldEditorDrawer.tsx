import { useState, useEffect } from "react";
import { useReactFlow } from "@xyflow/react";
import { Plus, Trash2, X, Save } from "lucide-react";
import { useCustomAgentStore, CustomField } from "../store/customAgentStore";

export function FieldEditorDrawer() {
  const { isOpen, activeNodeId, customFields, closeDrawer } = useCustomAgentStore();
  const { setNodes } = useReactFlow();
  
  const [fields, setFields] = useState<CustomField[]>([]);

  useEffect(() => {
    if (isOpen) {
      setFields(customFields.length > 0 ? [...customFields] : [{ name: "", type: "string", description: "" }]);
    }
  }, [isOpen, customFields]);

  if (!isOpen) return null;

  const addField = () => setFields([...fields, { name: "", type: "string", description: "" }]);

  const updateField = (index: number, key: keyof CustomField, value: string) => {
    const newFields = [...fields];
    newFields[index][key] = value;
    setFields(newFields);
  };

  const removeField = (index: number) => {
    const newFields = [...fields];
    newFields.splice(index, 1);
    setFields(newFields);
  };

  const handleSaveAndClose = () => {
    if (!activeNodeId) return;

    const customSchema: Record<string, { type: string; description: string }> = {};
    fields.forEach((f) => {
      if (f.name.trim()) {
        customSchema[f.name.trim()] = {
          type: f.type,
          description: f.description,
        };
      }
    });

    setNodes((nds) =>
      nds.map((n) =>
        n.id === activeNodeId
          ? { ...n, data: { ...n.data, customFields: fields, customSchema } }
          : n
      )
    );

    closeDrawer();
  };

  return (
    <div className="absolute right-4 top-20 bottom-4 w-[360px] bg-white z-50 shadow-lg flex flex-col border border-gray-200 rounded-xl overflow-hidden">
      <div className="flex-shrink-0 flex items-center justify-between p-4 border-b border-gray-100 bg-gray-50">
        <h2 className="text-lg font-semibold text-slate-800">Configure Fields</h2>
        <button onClick={closeDrawer} className="p-1 text-gray-400 hover:text-gray-600 rounded">
          <X className="w-5 h-5" />
        </button>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto p-4 flex flex-col gap-3">
        {fields.map((field, index) => (
          <div key={index} className="flex flex-col gap-2 bg-gray-50 p-3 rounded-lg border border-gray-200 shadow-sm">
            <div className="flex items-center gap-2">
              <input
                type="text"
                placeholder="Field Name"
                value={field.name}
                onChange={(e) => updateField(index, "name", e.target.value)}
                className="flex-1 min-w-0 text-sm p-2 border border-gray-200 rounded focus:outline-none focus:border-blue-400 bg-white"
              />
              <select
                value={field.type}
                onChange={(e) => updateField(index, "type", e.target.value)}
                className="w-28 text-sm p-2 border border-gray-200 rounded focus:outline-none focus:border-blue-400 bg-white"
              >
                <option value="string">String</option>
                <option value="number">Number</option>
                <option value="boolean">Boolean</option>
              </select>
              <button onClick={() => removeField(index)} className="p-2 text-gray-400 hover:text-red-500 rounded bg-white border border-gray-200">
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
            <input
              type="text"
              placeholder="AI Hint / Description"
              value={field.description}
              onChange={(e) => updateField(index, "description", e.target.value)}
              className="w-full text-sm p-2 border border-gray-200 rounded focus:outline-none focus:border-blue-400 bg-white"
            />
          </div>
        ))}

        <button
          onClick={addField}
          className="flex items-center justify-center gap-2 w-full py-3 mt-2 border border-dashed border-blue-300 text-blue-600 rounded-lg hover:bg-blue-50 text-sm font-medium transition-colors"
        >
          <Plus className="w-4 h-4" />
          Add New Field
        </button>
      </div>

      <div className="flex-shrink-0 p-4 border-t border-gray-100 bg-white">
        <button
          onClick={handleSaveAndClose}
          className="flex items-center justify-center gap-2 w-full py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-semibold transition-colors shadow-sm"
        >
          <Save className="w-4 h-4" />
          Save & Close
        </button>
      </div>
    </div>
  );
}
