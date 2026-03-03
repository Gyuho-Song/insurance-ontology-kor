import { demoCustomers, getCustomerById } from '@/lib/customers';

describe('customers', () => {
  it('should have exactly 10 customers', () => {
    expect(demoCustomers).toHaveLength(10);
  });

  it('each customer should have required fields', () => {
    demoCustomers.forEach((customer) => {
      expect(customer.id).toBeTruthy();
      expect(customer.name).toBeTruthy();
      expect(customer.products.length).toBeGreaterThanOrEqual(2);
      customer.products.forEach((p) => {
        expect(p.policy_name).toBeTruthy();
        expect(p.product_type).toBeTruthy();
      });
    });
  });

  it('all customer IDs should be unique', () => {
    const ids = demoCustomers.map((c) => c.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  describe('getCustomerById', () => {
    it('should return the correct customer', () => {
      const park = getCustomerById('CUSTOMER_PARK');
      expect(park).toBeDefined();
      expect(park!.name).toBe('박지영');
    });

    it('should return undefined for unknown id', () => {
      expect(getCustomerById('UNKNOWN')).toBeUndefined();
    });
  });
});
