
export async function withTimeout<T>(promise: Promise<T>, timeout: number): Promise<T> {
    return Promise.race([
        promise,
        new Promise<T>((_, reject) =>
            setTimeout(() => reject(new Error(`Timeout after ${timeout}ms`)), timeout)
        )
    ]);
}


export function getRandomInt(min: number, max: number) {
    const minCeiled = Math.ceil(min);
    const maxFloored = Math.floor(max + 1);
    return Math.floor(Math.random() * (maxFloored - minCeiled) + minCeiled);
}
