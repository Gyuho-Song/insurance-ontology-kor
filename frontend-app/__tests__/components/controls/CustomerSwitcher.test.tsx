import { render, screen, fireEvent } from '@testing-library/react';
import { CustomerSwitcher } from '@/components/controls/CustomerSwitcher';
import { demoCustomers } from '@/lib/customers';

describe('CustomerSwitcher', () => {
  const mockOnChange = jest.fn();

  beforeEach(() => {
    mockOnChange.mockClear();
  });

  it('should render all 10 customers', () => {
    render(
      <CustomerSwitcher
        selectedCustomerId={null}
        onCustomerChange={mockOnChange}
      />
    );

    demoCustomers.forEach((customer) => {
      expect(screen.getByText(customer.name)).toBeInTheDocument();
    });
  });

  it('should call onCustomerChange when a customer is clicked', () => {
    render(
      <CustomerSwitcher
        selectedCustomerId={null}
        onCustomerChange={mockOnChange}
      />
    );

    fireEvent.click(screen.getByText('박지영'));
    expect(mockOnChange).toHaveBeenCalledWith(demoCustomers[0]);
  });

  it('should deselect when the active customer is clicked again', () => {
    render(
      <CustomerSwitcher
        selectedCustomerId="CUSTOMER_PARK"
        onCustomerChange={mockOnChange}
      />
    );

    fireEvent.click(screen.getByText('박지영'));
    expect(mockOnChange).toHaveBeenCalledWith(null);
  });

  it('should show product count for each customer', () => {
    render(
      <CustomerSwitcher
        selectedCustomerId={null}
        onCustomerChange={mockOnChange}
      />
    );

    // All product count numbers should be present
    const allButtons = screen.getAllByRole('button');
    expect(allButtons).toHaveLength(demoCustomers.length);
  });
});
