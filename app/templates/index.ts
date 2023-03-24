import { asjson, serializeFormData, findEntry } from './lib'
(function () {
    const form = document.getElementById('myform') as HTMLFormElement
    const result = document.getElementById('result') as HTMLElement
    const json_result = document.getElementById('result-json') as HTMLElement

    form.addEventListener('submit', async (e) => {
        e.preventDefault()
        // e.stopPropagation()
        result.textContent = ''
        const formData = new FormData(form)
        for (const [key, value] of formData) {
            result.textContent += `${key}: ${value}\n`;
        }

        console.log('any checked?', formData.has('checked'))

        try {
            const resp = await fetch(form.action, { method: 'post', body: formData })
            const json = await resp.json()
            json_result.textContent = JSON.stringify(json)
            console.log(resp.ok, json, new Date(json.date))
            if (resp.status === 400) {
                for (const [i, msg] of findEntry(form, json)) {
                    (i as HTMLElement).classList.add('invalid')
                }
            }

            // as json
            const obj = JSON.stringify(await serializeFormData(formData))
            const resp1 = await fetch(form.action, {
                method: 'post',
                body: obj,
                headers: {
                    "Content-Type": "application/json",
                }
            })
            const json1 = await resp1.json()
            console.log(resp1.ok, json1)
        } catch (e) {
            console.log('err', e)
        }

    })

})();

(function () {

    const json1 = document.getElementById('json1') as HTMLButtonElement
    const result1 = document.getElementById('json1-result') as HTMLElement
    const arg5 = [{ query: 's' }, { query: 'p' }]
    json1.addEventListener('click', async (e) => {
        const resp = await fetch('/arg5', asjson({ extra: arg5 }))
        const json = await resp.json()
        console.log(resp.ok, json, typeof json)
        result1.textContent = JSON.stringify(json)
    })
})();

(function () {
    const form = document.getElementById('filestorage') as HTMLFormElement
    const result = document.getElementById('filestorage-result') as HTMLElement


    form.addEventListener('submit', async (e) => {
        e.preventDefault()
        // e.stopPropagation()
        const formData = new FormData(form)

        // this works with a File object

        try {
            const resp = await fetch(form.action, { method: 'post', body: formData })
            const json = await resp.json()
            console.log(resp.ok, resp.status === 200, json)
            result.textContent = JSON.stringify(json)
        } catch (e) {
            console.log('err', e)
        }

    })

})();


import type { ArgXX, FuncArg5 } from './types'

const aa: ArgXX[] = [{
    query: 'qqvvvqqq'
}, { query: 'xxxx2' }];


const b: FuncArg5 = {
    extra: aa,
};


(async function () {
    const resp = await fetch('/arg5', asjson(b))
    const json = await resp.json()
    console.log(resp.ok, json)
})();
