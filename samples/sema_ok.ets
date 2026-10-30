// samples/sema_ok.ets
// 语义正确的样例：类型标注完整、接口已实现、装饰器位置合法

interface Greeter {
  greet(name: string): string;
}

class Person implements Greeter {
  private id: number = 0;
  name: string = 'nobody';

  constructor(id: number, name: string) {
    this.id = id;
    this.name = name;
  }

  greet(name: string): string {
    return 'Hello, ' + name;
  }

  getId(): number {
    return this.id;
  }
}

@Entry
@Component
struct Counter {
  @State count: number = 0;
  @Prop step: number = 1;

  increment(step: number): void {
    this.count = this.count + step;
  }

  build() {
    Column() {
      Text('count')
      Button('+1')
        .onClick(() => {
          this.increment(1);
        })
    }
  }
}

function fib(n: number): number {
  let a: number = 0;
  let b: number = 1;
  for (let i: number = 0; i < n; i++) {
    let t: number = a + b;
    a = b;
    b = t;
  }
  return a;
}