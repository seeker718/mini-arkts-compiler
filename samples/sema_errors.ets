// samples/sema_errors.ets
// 故意包含各类语义错误，用于验证语义分析器的定位与报错能力

@Component
struct NotEntry {
  @State count: number = 0;
}

@Entry
@Component
struct Bad {
  @State title: string = 0;
  @State hits: number = 0;

  add(a: number, b: number): number {
    let x: string = a + b;
    return x;
  }

  tryUse(): void {
    let y: number = unknownVar;
    let z: number = 'text';
    z = z + 'a';
    if (z) {
      this.hits = 1;
    }
  }

  dup(): void {
    let q: number = 1;
    let q: number = 2;
  }

  wrongArgs(): void {
    this.add(1);
    this.add('a', 1);
  }
}

class Base {
  private secret: number = 1;
  value: number = 2;
}

function outside(): number {
  let b: Base = new Base();
  let s: number = b.secret;
  return s;
}

interface Shape {
  area(): number;
}

class Circle implements Shape {
  radius: number = 1;
}