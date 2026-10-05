import React, { useMemo } from 'react';

const ExceptionTab = ({ exceptionRules = [], unifiedPayload = {} }: { exceptionRules: any[], unifiedPayload: any }) => {
  // Evaluate rules against the payload
  const activeExceptions = useMemo(() => {
    if (!unifiedPayload || !exceptionRules.length) return [];

    const exceptions: any[] = [];

    const getNestedValue = (obj: any, path: string) => {
      return path.split('.').reduce((acc, part) => acc && acc[part], obj);
    };

    const hasDocument = (docType: string) => {
      if (docType === 'INSURANCE') return !!unifiedPayload.lossRuns?.claims;
      if (docType === 'WORK_COMP') return !!unifiedPayload.acord?.data || !!unifiedPayload.acord?.demographics;
      if (docType === 'EXPERIENCE_MODIFIER') return !!unifiedPayload.modifierData;
      return false;
    };

    const daysSince = (dateStr: string) => {
      if (!dateStr) return Infinity;
      const date = new Date(dateStr);
      if (isNaN(date.getTime())) return Infinity;
      const diffTime = Math.abs(new Date().getTime() - date.getTime());
      return Math.ceil(diffTime / (1000 * 60 * 60 * 24)); 
    };

    exceptionRules.forEach((rule) => {
      let isExceptionRaised = false;

      try {
        if (rule.condition === "!demographics.fein") {
          const fein = getNestedValue(unifiedPayload, 'acord.demographics.fein') || getNestedValue(unifiedPayload, 'acord.data.demographics.fein');
          if (!fein) isExceptionRaised = true;
        } 
        else if (rule.condition === "!has_document('INSURANCE')") {
          if (!hasDocument('INSURANCE')) isExceptionRaised = true;
        } 
        else if (rule.condition === "days_since(report_metadata.valuation_date) > 60") {
          const valDate = getNestedValue(unifiedPayload, 'lossRuns.report_metadata.valuation_date') || getNestedValue(unifiedPayload, 'lossRuns.data.report_metadata.valuation_date');
          if (daysSince(valDate) > 60) isExceptionRaised = true;
        } 
        else if (rule.condition === "summary.employee_count == 0") {
          const empCount = getNestedValue(unifiedPayload, 'metadata.totalEmployees');
          if (empCount === 0 || empCount === "0") isExceptionRaised = true;
        } 
        else if (rule.condition === "!has_document('EXPERIENCE_MODIFIER')") {
          if (!hasDocument('EXPERIENCE_MODIFIER')) isExceptionRaised = true;
        } 
        else if (rule.condition === "!has_document('WORK_COMP')") {
          if (!hasDocument('WORK_COMP')) isExceptionRaised = true;
        }
      } catch (err) {
        console.error(`Error evaluating rule ${rule.id}`, err);
      }

      if (isExceptionRaised) {
        exceptions.push({
          id: rule.id,
          message: rule.exception_message,
        });
      }
    });

    return exceptions;
  }, [exceptionRules, unifiedPayload]);

  return (
    <div className="p-4 bg-white rounded-lg shadow mt-4">
      <h3 className="text-lg font-semibold text-red-600 mb-4 flex items-center">
        <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        Exceptions Detected ({activeExceptions.length})
      </h3>

      {activeExceptions.length === 0 ? (
        <div className="text-gray-500 text-sm">No exceptions found. All criteria met.</div>
      ) : (
        <table className="min-w-full divide-y divide-gray-200 border">
          <thead className="bg-red-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-red-800 uppercase tracking-wider">
                Exception
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {activeExceptions.map((exception, idx) => (
              <tr key={idx} className="hover:bg-red-50 transition-colors">
                <td className="px-6 py-4 whitespace-nowrap text-sm text-red-700 font-medium">
                  {exception.message}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
};

export default ExceptionTab;
