import React from 'react';
import { Search } from 'lucide-react';
import { Input } from './Input';
import { cn } from '../../lib/utils';

interface SearchInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  className?: string;
}

export function SearchInput({ className, ...props }: SearchInputProps) {
  return (
    <div className={cn('relative', className)}>
      <Search className="absolute left-2 top-3 h-4 w-4 text-muted-foreground" />
      <Input
        className="pl-8"
        placeholder="Search projects..."
        type="search"
        {...props}
      />
    </div>
  );
} 