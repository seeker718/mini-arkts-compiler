// samples/ir_demo.ets
// 供实验三使用：包含顺序执行、分支、循环、函数调用与 SSA 汇合点（φ）

function square(x: number): number {
  return x * x;
}

function sumTo(n: number): number {
  let total: number = 0;
  let i: number = 1;
  while (i <= n) {
    total = total + i;
    i++;
  }
  return total;
}

function classify(value: number): number {
  let result: number = 1;
  if (value > 100) {
    result = 2;
  } else {
    result = result + 0;
  }
  return result;
}

function demo(): number {
  let n: number = 10;
  let sq: number = square(n);
  let s: number = sumTo(n);
  let c: number = classify(s);
  return sq + s + c;
}