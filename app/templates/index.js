(function () {
    const form = document.getElementById('myform')
    const result = document.getElementById('result')

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
            console.log(resp.ok, json)
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
    json1.addEventListener('click', async (e) => {
        const resp = await fetch('/json', { method: 'post' })
        const json = await resp.json()
        console.log(resp.ok, json, typeof json)
        //await getit(form.action, new FormData(form))
    })
})();

(function () {
    const form = document.getElementById('filestorage')


    form.addEventListener('submit', async (e) => {
        e.preventDefault()
        // e.stopPropagation()
        const formData = new FormData(form)

        // this works with a File object

        try {
            const resp = await fetch(form.action, { method: 'post', body: formData })
            const json = await resp.json()
            console.log(resp.ok, resp.status === 200, json)
        } catch (e) {
            console.log('err', e)
        }

    })

})();

async function serializeFormData(formData) {
    const obj = {}

    async function cvt(value) {
        if (value instanceof File) {
            return await value.text()
        }
        return value
    }

    for (let [key, value] of formData.entries()) {
        const o = obj[key]
        value = await cvt(value)
        if (o === undefined) {
            obj[key] = value;
        } else if (Array.isArray(o)) {
            o.push(value)
        } else {
            obj[key] = [o, value]
        }

    }
    return obj;
};
