// samples/optimize_demo.ets
// 含可被 AOT 优化 Pass 化简的代码：常量折叠与死代码消除

function foldConstants(): number {
  let a: number = 2 + 3 * 4;
  let b: number = (1 + 2) * (3 + 4);
  let c: number = a + b;
  return c;
}

function deadCode(flag: boolean): number {
  let x: number = 10;
  if (false) {
    x = 999;
  }
  if (true) {
    x = x + 1;
  }
  let unused: number = x * 100;
  return x;
}

function demo(): number {
  let a: number = foldConstants();
  let b: number = deadCode(true);
  return a + b;
}