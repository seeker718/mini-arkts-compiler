// samples/algorithms.ets
// 纯函数与流程控制：函数、for、while、if-else-if、数组、复合赋值、逻辑运算

function fib(n: number): number {
  let a: number = 0;
  let b: number = 1;
  for (let i = 0; i < n; i++) {
    let t: number = a + b;
    a = b;
    b = t;
  }
  return a;
}

function sum(values: number[]): number {
  let total: number = 0;
  let i: number = 0;
  while (i < values.length) {
    total += values[i];
    i++;
  }
  return total;
}

function classify(score: number): string {
  if (score >= 90 && score <= 100) {
    return 'excellent';
  } else if (score >= 60) {
    return 'pass';
  } else {
    return 'fail';
  }
}

function demo(): void {
  let values: number[] = [1, 2, 3, 4, 5];
  let n: number = fib(10);
  let s: number = sum(values);
  let flag: boolean = n > s ? true : false;
  console.log(classify(s), flag);
}