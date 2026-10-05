export type PageInput = {
  page: number;
  pageSize: number;
};

export type PageOutput<T> = {
  items: T[];
  page: number;
  pageSize: number;
  total: number;
};
