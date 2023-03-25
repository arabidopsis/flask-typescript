export type Json = string | string[] | { [key: string]: Json };
export type ValidationError = {
    loc: string[]
    msg: string
    type: string
}

export function asjson(obj: any): RequestInit {
    return {
        method: 'post',
        body: JSON.stringify(obj), headers: {
            "Content-Type": "application/json",
        }
    }
}

export async function serializeFormData(formData: FormData): Promise<Record<string, Json>> {
    // seems to change textarea '\r\n' to '\n'?
    const obj: Record<string, Json> = {}

    async function cvt(value: FormDataEntryValue): Promise<string> {
        if (value instanceof File) {
            return await value.text()
        }
        return value
    }


    function fetch_tgt(key: string, tgt: Record<string, Json>): [string, Record<string, Json>] {
        const kl = key.split('.')
        for (let i = 0; i < kl.length - 1; i++) {
            key = kl[i]
            const o = tgt[key]
            if (o === undefined) {
                tgt = tgt[key] = {}
            } else {
                if (typeof o === "string" || Array.isArray(o)) {
                    throw new Error("malformed dotted names!")
                }
                tgt = o
            }
        }
        return [kl[kl.length - 1], tgt]
    }

    for (let [key_, value] of formData) {
        let [key, tgt] = fetch_tgt(key_, obj)

        const o = tgt[key]
        let svalue = await cvt(value)
        if (o === undefined) {
            tgt[key] = svalue;
        } else if (Array.isArray(o)) {
            o.push(svalue)
        } else {
            if (!(typeof o === 'string')) {
                throw new Error("malformed dotted names!")
            }
            tgt[key] = [o, svalue]
        }

    }
    return obj;
};


export function findErrors(form: HTMLFormElement, errors: ValidationError[]): [HTMLElement, string][] {
    const ret: [HTMLElement, string][] = []
    for (const error of errors) {
        const name: string = error.loc.join('.') as string
        let i = form.elements.namedItem(name) as HTMLElement
        if (i === null) {
            continue
        }
        if (i instanceof RadioNodeList) {
            i = i.item(0) as HTMLElement
            if (i === null) {
                continue
            }
        }
        ret.push([i, error.msg])
    }
    return ret;
}
