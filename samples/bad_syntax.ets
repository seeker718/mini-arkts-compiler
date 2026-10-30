// samples/bad_syntax.ets
// 故意包含词法/语法错误，用于验证错误处理与恢复能力（实验一的「处理错误」要求）

let x = ;
let s = 'unterminated string
function broken( {
  return 1;
}
let 123abc = 4;
let ok: number = 10
let after: number = 99;