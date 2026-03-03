'use client';

import { demoCustomers, type DemoCustomer } from '@/lib/customers';
import { cn } from '@/lib/utils';

interface CustomerSwitcherProps {
  selectedCustomerId: string | null;
  onCustomerChange: (customer: DemoCustomer | null) => void;
}

export function CustomerSwitcher({ selectedCustomerId, onCustomerChange }: CustomerSwitcherProps) {
  const handleClick = (customer: DemoCustomer) => {
    if (selectedCustomerId === customer.id) {
      onCustomerChange(null); // Deselect → back to general mode
    } else {
      onCustomerChange(customer);
    }
  };

  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      <span className="text-xs text-muted-foreground whitespace-nowrap">마이데이터:</span>
      {demoCustomers.map((customer) => {
        const isActive = selectedCustomerId === customer.id;
        return (
          <button
            key={customer.id}
            title={customer.products.map((p) => p.policy_name).join(', ')}
            className={cn(
              'rounded-md px-2 py-1 text-xs transition-colors',
              isActive
                ? 'bg-emerald-600 text-white'
                : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'
            )}
            onClick={() => handleClick(customer)}
          >
            <span>{customer.name}</span>
            <span className="ml-0.5 opacity-70">{customer.products.length}</span>
          </button>
        );
      })}
    </div>
  );
}
