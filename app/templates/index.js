(function () {
    const form = document.getElementById('myform')
    const result = document.getElementById('result')
    const json_result = document.getElementById('result-json')

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
                showError(form, json)
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




    const json1 = document.getElementById('json1')
    const result1 = document.getElementById('json1-result')
    const arg5 = [{ query: 's' }, { query: 'p' }]
    json1.addEventListener('click', async (e) => {
        const resp = await fetch('/arg5', asjson({ extra: arg5 }))
        const json = await resp.json()
        console.log(resp.ok, json, typeof json)
        result1.textContent = JSON.stringify(json)
    })
})();

(function () {
    const form = document.getElementById('filestorage')
    const result = document.getElementById('filestorage-result')


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

function asjson(obj) {
    return {
        method: 'post',
        body: JSON.stringify(obj), headers: {
            "Content-Type": "application/json",
        }
    }
}

function showError(form, errors) {
    for (const error of errors) {
        const name = error.loc.join('.')
        const i = form.elements[name]
        if (i instanceof NodeList) {
            i = i[0]
        }
        i.classList.add('invalid')
    }
}
async function serializeFormData(formData) {
    // seems to change textarea '\r\n' to '\n'?
    const obj = {}

    async function cvt(value) {
        if (value instanceof File) {
            return await value.text()
        }
        return value
    }

    function fetch_tgt(key, tgt) {
        const kl = key.split('.')
        for (let i = 0; i < kl.length - 1; i++) {
            key = kl[i]
            const o = tgt[key]
            if (o === undefined) {
                tgt = tgt[key] = {}
            } else {
                tgt = o
            }
        }
        return [kl[kl.length - 1], tgt]
    }

    for (let [key_, value] of formData) {
        let [key, tgt] = fetch_tgt(key_, obj)

        const o = tgt[key]
        value = await cvt(value)
        if (o === undefined) {
            tgt[key] = value;
        } else if (Array.isArray(o)) {
            o.push(value)
        } else {
            tgt[key] = [o, value]
        }

    }
    console.log(obj)
    return obj;
};
