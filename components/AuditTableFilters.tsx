import React from 'react';
import { Filter } from 'lucide-react';

export type FilterType = 'all' | 'verified' | 'partial' | 'unverified';

interface AuditTableFiltersProps {
  filter: FilterType;
  onFilterChange: (value: FilterType) => void;
}

const AuditTableFilters: React.FC<AuditTableFiltersProps> = ({ filter, onFilterChange }) => {
  return (
    <div className="flex-shrink-0 px-6 py-2 border-b border-slate-100 bg-white flex items-center gap-3">
      <div className="flex items-center gap-1">
        <Filter className="w-3.5 h-3.5 text-slate-400" />
        <select 
          value={filter}
          onChange={(e) => onFilterChange(e.target.value as FilterType)}
          className="text-xs font-medium text-slate-600 bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-300"
        >
          <option value="all">All Claims</option>
          <option value="unverified">Risks Only</option>
          <option value="partial">Partial Only</option>
          <option value="verified">Verified Only</option>
        </select>
      </div>
    </div>
  );
};

export default AuditTableFilters;


