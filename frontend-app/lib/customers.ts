export interface CustomerProduct {
  policy_name: string;
  product_type: string;
}

export interface DemoCustomer {
  id: string;
  name: string;
  products: CustomerProduct[];
}

export const demoCustomers: DemoCustomer[] = [
  {
    id: 'CUSTOMER_PARK',
    name: '박지영',
    products: [
      { policy_name: 'H종신보험', product_type: 'whole_life' },
      { policy_name: 'e건강보험', product_type: 'health' },
    ],
  },
  {
    id: 'CUSTOMER_KIM',
    name: '김민수',
    products: [
      { policy_name: '시그니처H암보험', product_type: 'cancer' },
      { policy_name: '포켓골절보험', product_type: 'fracture' },
    ],
  },
  {
    id: 'CUSTOMER_LEE',
    name: '이준혁',
    products: [
      { policy_name: 'H간병보험', product_type: 'care' },
      { policy_name: '경영인H정기보험', product_type: 'term' },
    ],
  },
  {
    id: 'CUSTOMER_CHOI',
    name: '최서연',
    products: [
      { policy_name: 'e암보험(비갱신형)', product_type: 'cancer' },
      { policy_name: '상속H종신보험', product_type: 'whole_life' },
    ],
  },
  {
    id: 'CUSTOMER_JUNG',
    name: '정하나',
    products: [
      { policy_name: 'Need AI 암보험', product_type: 'cancer' },
      { policy_name: '시그니처H통합건강보험', product_type: 'health' },
    ],
  },
  {
    id: 'CUSTOMER_HAN',
    name: '한도윤',
    products: [
      { policy_name: '제로백H종신보험', product_type: 'whole_life' },
      { policy_name: 'H당뇨보험', product_type: 'diabetes' },
    ],
  },
  {
    id: 'CUSTOMER_SONG',
    name: '송민지',
    products: [
      { policy_name: '케어백간병플러스보험', product_type: 'care' },
      { policy_name: '상생친구 보장보험', product_type: 'guarantee' },
    ],
  },
  {
    id: 'CUSTOMER_YOON',
    name: '윤재호',
    products: [
      { policy_name: 'H종신보험', product_type: 'whole_life' },
      { policy_name: '시그니처H암보험', product_type: 'cancer' },
      { policy_name: '포켓골절보험', product_type: 'fracture' },
    ],
  },
  {
    id: 'CUSTOMER_KANG',
    name: '강수빈',
    products: [
      { policy_name: 'e건강보험', product_type: 'health' },
      { policy_name: 'e암보험(비갱신형)', product_type: 'cancer' },
      { policy_name: 'H간병보험', product_type: 'care' },
    ],
  },
  {
    id: 'CUSTOMER_LIM',
    name: '임태현',
    products: [
      { policy_name: '상속H종신보험', product_type: 'whole_life' },
      { policy_name: 'Need AI 암보험', product_type: 'cancer' },
      { policy_name: '제로백H종신보험 간편가입', product_type: 'whole_life' },
    ],
  },
];

export function getCustomerById(id: string): DemoCustomer | undefined {
  return demoCustomers.find((c) => c.id === id);
}
